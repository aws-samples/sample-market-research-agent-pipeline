import json
import boto3
import math
import re
import os
from datetime import datetime, timezone
from scipy import spatial
from botocore.config import Config

timeout_config = Config(read_timeout=300)
retry_config = Config(
    read_timeout=300,
    retries={'total_max_attempts': 4, 'mode': 'standard'}
)


s3 = boto3.client("s3", config=timeout_config)
bedrock = boto3.client("bedrock-runtime", config=retry_config)
sts = boto3.client("sts", config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()["Account"]

MODEL_ID = os.environ['EMBEDDING_MODEL_FOR_KB']  # Titan Embeddings

BEDROCK_MODEL_ID = os.environ['MODEL_INFERENCE_PROFILE']

CONTENT_TYPE_JSON = "application/json"

# ---------- helpers ----------
def get_embedding(text: str):
    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({"inputText": text}),
        contentType=CONTENT_TYPE_JSON,
        accept=CONTENT_TYPE_JSON,
    )
    result = json.loads(response["body"].read())
    return result["embedding"]


def cosine_similarity(v1, v2):
    cosine_distance = spatial.distance.cosine(v1, v2)
    similarity_score = 1 - cosine_distance
    return similarity_score


def parse_s3_uri(uri):
    uri = uri.replace("s3://", "")
    bucket, key = uri.split("/", 1)
    return bucket, key

def list_s3_uris(bucket, prefix):
    try:
        print("bucket:", bucket, type(bucket))
        print("prefix:", prefix, type(prefix)) 
        uris = []
        paginator = s3.get_paginator("list_objects_v2") 
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                uris.append(f"s3://{bucket}/{key}")

        return uris
    except Exception as e:
        print(f"Error listing S3 URIs: {str(e)}")  

def extract_json(text: str):
    text = text.strip()

    # Remove code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Extract first JSON block (non-greedy)
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")

    json_str = match.group()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print("Invalid JSON from model:\n", json_str)
        raise e 


def invoke_and_parse_json(client, model_id, body, max_retries=2):
    """Invoke the model, parse JSON from the response, and retry on invalid JSON."""
    messages = body.get("messages", [])
    for attempt in range(max_retries + 1):
        body["messages"] = list(messages)  # reset messages each attempt
        if attempt > 0:
            # Add corrective nudge for retry attempts
            body["messages"].append({"role": "assistant", "content": model_output})
            body["messages"].append({"role": "user", "content": "Your previous response was not valid JSON. Please respond ONLY with a valid JSON object, no markdown, no explanation."})

        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType=CONTENT_TYPE_JSON,
            accept=CONTENT_TYPE_JSON,
        )
        response_body = json.loads(response["body"].read())
        model_output = response_body["content"][0]["text"]
        print(f"Model output (attempt {attempt+1}): {model_output}")

        try:
            return extract_json(model_output)
        except (json.JSONDecodeError, ValueError) as e:
            if attempt < max_retries:
                print(f"JSON parse failed (attempt {attempt+1}/{max_retries+1}), retrying: {e}")
            else:
                print(f"JSON parse failed after {max_retries+1} attempts. Raw output: {model_output}")
                raise

def get_summary(system_prompt, user_prompt):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "temperature": 0,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    }

    parsed_output = invoke_and_parse_json(bedrock, BEDROCK_MODEL_ID, body)
    print("parsed output is: ", parsed_output)

    return parsed_output 

def greedy_clusters(vectors_by_uri, threshold):
    remaining = list(vectors_by_uri.keys())
    clusters = []

    while remaining:
        leader = remaining.pop(0)
        leader_vec = vectors_by_uri[leader]

        cluster = [leader]
        to_remove = []

        for uri in remaining:
            sim = cosine_similarity(leader_vec, vectors_by_uri[uri])
            if sim >= threshold:
                cluster.append(uri)
                to_remove.append(uri)

        # remove grouped items
        for uri in to_remove:
            remaining.remove(uri)

        clusters.append(cluster)

    return clusters


def process_clusters(category, clusters, system_prompt):
    individual_files = 0
    merged_files = 0
    raw_content_output_bucket = os.environ['RAW_CONTENT_OUTPUT_BUCKET']
    s3_uris_to_return = []
    for cluster in clusters:
        if len(cluster) == 0:
            print ("cluster length found to be zero, something went wrong, as there should be minimum one s3 uri in clusters if we have come till here")
            return {"error": "no clusters generated"}
        if len(cluster) == 1:
            uri = cluster[0]
            bucket, key = parse_s3_uri(uri)

            obj = s3.get_object(Bucket=bucket, Key=key, ExpectedBucketOwner=ACCOUNT_ID)
            data = json.loads(obj["Body"].read())

            data['s3_uri'] = uri
            # data['urls'] = [data['url']] if 'url' in data else []  

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
            base_prefix = "/".join(key.split("/")[:-1])

            processed_key = f"{base_prefix}/individual_news_{timestamp}.json"

            data = [data]
            s3.put_object(
                Bucket=raw_content_output_bucket,
                Key=processed_key,
                Body=json.dumps(data).encode("utf-8"),
                ExpectedBucketOwner=ACCOUNT_ID
            ) 
            individual_files += 1
            s3_uris_to_return.append(f"s3://{raw_content_output_bucket}/{processed_key}") 

        if len(cluster) > 1:
            research_topic = None 

            merged_data = []


            temp_count = 0
            for uri in cluster:
                bucket, key = parse_s3_uri(uri)

                base_prefix = "/".join(key.split("/")[:-1])  # remove file name

                obj = s3.get_object(Bucket=bucket, Key=key, ExpectedBucketOwner=ACCOUNT_ID)
                data = json.loads(obj["Body"].read())
                data['s3_uri'] = uri 
                
                research_topic = data.get('research_topic','')

                merged_data.append(data)
                temp_count += 1

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
            processed_key = f"{base_prefix}/similar_combined_{timestamp}.json"

            s3.put_object(
                Bucket=raw_content_output_bucket,
                Key=processed_key,
                Body=json.dumps(merged_data).encode("utf-8"),
                ExpectedBucketOwner=ACCOUNT_ID
            ) 
            merged_files += temp_count 
            s3_uris_to_return.append(f"s3://{raw_content_output_bucket}/{processed_key}") 


    return {"individual_files": individual_files, "merged_files": merged_files, "output_bucket": raw_content_output_bucket, "prefix": f"{base_prefix}", "s3_uris": s3_uris_to_return}   


# ---------- lambda ----------
def lambda_handler(event, context):

    print("event is: ", event)
    
    parts = event['path'].strip("/").split("/")
    category = parts[-1]
    prefix = "/".join(parts) + "/"
    print("prefix is: ",prefix)
    print("category is: ",category)


    ###  SYSTEM PROMPTS  ###

    COMPETITIVE_LANDSCAPE_SUMMARY_PROMPT = """
You are a specialized market research intelligence summarization agent focused on competitive landscape content.

Your task is to create a comprehensive, strategically-focused summary of competitive intelligence content.

Input:
- research_topic: a market segment, industry, or competitive arena
- category: competitive_landscape
- content: article or news text containing competitive intelligence information

Guidelines:
- Focus on strategic moves, product launches, market positioning changes, and competitive dynamics
- Preserve all quantitative data (market share figures, revenue numbers, pricing, growth rates, investment amounts)
- Highlight key companies involved, their strategic intent, affected market segments, and competitive implications
- Include technology capabilities, product differentiators, go-to-market strategies, and customer impact
- Maintain analytical precision and use appropriate industry terminology
- Ensure no critical competitive signals, market shifts, or strategic pivots are omitted
- Keep the summary concise yet comprehensive, typically 150-250 words depending on content complexity
- Structure the summary logically: what happened → market context → competitive impact → strategic implications

Do not wrap the output in markdown or code blocks. Return raw JSON only.
Do not include any additional text, explanations, or formatting outside the JSON.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations.
Escape all double quotes inside string values.
Ensure the JSON is syntactically valid.

Respond ONLY with valid JSON in the following format:

{
  "summary": "..."
}


"""

    DEALS_PARTNERSHIPS_SUMMARY_PROMPT = """
You are a specialized market research intelligence summarization agent focused on deals, partnerships, and business development content.

Your task is to create a comprehensive, business-focused summary of deal and partnership content.

Input:
- research_topic: a market segment, industry, or deal arena
- category: deals_and_partnerships
- content: article or news text containing M&A, partnership, collaboration, or business development information

Guidelines:
- Focus on deal structures, financial terms, milestone payments, royalty arrangements, and territorial rights
- Preserve all monetary figures (upfront payments, total deal value, milestone amounts, equity investments)
- Highlight partner organizations, their roles, development responsibilities, and commercialization rights
- Include licensing agreements, co-development terms, acquisition details, integration plans, and strategic rationale
- Capture intellectual property arrangements, technology transfers, platform deals, and ecosystem implications
- Maintain business context including market opportunity, competitive positioning, and strategic fit
- Ensure no critical business terms, contingencies, or timeline commitments are omitted
- Keep the summary concise yet comprehensive, typically 150-250 words depending on content complexity
- Structure the summary logically: parties involved → deal terms → strategic rationale → future outlook

Do not wrap the output in markdown or code blocks. Return raw JSON only.
Do not include any additional text, explanations, or formatting outside the JSON.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations.
Escape all double quotes inside string values.
Ensure the JSON is syntactically valid.

Respond ONLY with valid JSON in the following format:


{ 
  "summary": "..."
}
"""
    OTHERS_SUMMARY_PROMPT = """
You are a specialized market research intelligence summarization agent focused on general industry content.

Your task is to create a comprehensive summary of market content that doesn't fall strictly into competitive landscape or deals/partnerships categories.

Input:
- research_topic: a market segment or industry
- category: others
- content: article or news text (may include regulatory updates, market analysis, policy changes, industry trends, technology shifts, etc.)

Guidelines:
- Focus on the primary theme: regulatory decisions, market dynamics, policy changes, industry trends, technology adoption, or workforce shifts
- Preserve all relevant facts, dates, regulatory body names, policy details, and quantitative information
- Highlight key stakeholders, affected parties, timelines, and implications for the research topic
- Include context about market impact, precedent-setting decisions, or broader industry significance
- Capture any forward-looking statements, anticipated changes, or strategic shifts
- Maintain objectivity and factual accuracy without speculation
- Ensure no critical regulatory requirements, compliance issues, or market-moving information is omitted
- Keep the summary concise yet comprehensive, typically 150-250 words depending on content complexity
- Structure the summary logically: main event/development → key details → stakeholder impact → broader implications

Do not wrap the output in markdown or code blocks. Return raw JSON only.
Do not include any additional text, explanations, or formatting outside the JSON.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations.
Escape all double quotes inside string values.
Ensure the JSON is syntactically valid.

Respond ONLY with valid JSON in the following format:

{
  "summary": "..."
}
"""
    cat_prompt_map = {"competitive_landscape": COMPETITIVE_LANDSCAPE_SUMMARY_PROMPT, "deals_and_partnerships": DEALS_PARTNERSHIPS_SUMMARY_PROMPT, "others": OTHERS_SUMMARY_PROMPT}

    s3_bucket = os.environ.get('CONTENT_STORE_BUCKET')

    s3_uris = list_s3_uris(s3_bucket, prefix)
    print("s3 uris are: ", s3_uris) 
    print(f"total no of files under category - {category} for prefix - {prefix} are {len(s3_uris)}") 
    
    if not s3_uris:
        clusters: [[]]
        print(f"no objects found under {event}") 
        return {"statusCode": 400, "body": json.dumps({"error": "no objects found at the s3 location given in event"})}
    

    vectors_by_uri = {}

    for uri in s3_uris:
        bucket, key = parse_s3_uri(uri)

        obj = s3.get_object(Bucket=bucket, Key=key, ExpectedBucketOwner=ACCOUNT_ID)
        data = json.loads(obj["Body"].read())
        
        user_prompt = f"""
            Research Topic: {data['research_topic']}

            Category: {category}

            Content: {data['content']}
            """
        parsed_output = get_summary(cat_prompt_map[category], user_prompt)

        summary_text = parsed_output.get("summary", "Failed to generate/extract summary.") if parsed_output else "Failed to generate/extract summary."
        data["summary"] = summary_text 
        embedding = get_embedding(summary_text)

        # write vector back into same file
        data["vector"] = embedding 

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data).encode("utf-8"),
            ExpectedBucketOwner=ACCOUNT_ID
        )

        vectors_by_uri[uri] = embedding


    uris = list(vectors_by_uri.keys())
    if len(uris) < 2:
        clusters = [uris]
        print(f"clusters for {event['path']} : ",clusters)
        process_clusters_response = process_clusters(category, clusters, cat_prompt_map[category]) 
        print("process_clusters_response: ",process_clusters_response)

        return [
            {
                "input_s3_uri": uri,
                "mode": "full" 
            }
            for uri in process_clusters_response['s3_uris']
        ] 

    threshold = float(os.environ["COSINE_SIMILARITY_THRESHOLD"])

    if not 0.0 <= threshold <= 1.0:
        raise ValueError("COSINE_SIMILARITY_THRESHOLD must be between 0 and 1") 

    similar_map = {}

    for i in range(len(uris)):
        for j in range(i + 1, len(uris)):
            u1, u2 = uris[i], uris[j]

            sim = cosine_similarity(vectors_by_uri[u1], vectors_by_uri[u2])

            # if sim > 0.85:  # similarity threshold  
            similar_map.setdefault(u1, []).append({"uri": u2, "score": sim})
            similar_map.setdefault(u2, []).append({"uri": u1, "score": sim})
    
    print(f"similarity map for {event['path']}: {similar_map}") 

    clusters = greedy_clusters(vectors_by_uri=vectors_by_uri, threshold= threshold)

    print(f"clusters for {event['path']} : ",clusters)

    process_clusters_response = process_clusters(category, clusters, cat_prompt_map[category]) 
    print("process_clusters_response: ",process_clusters_response)

    return [
        {
            "input_s3_uri": uri,
            "mode": "full" 
        }
        for uri in process_clusters_response['s3_uris']
    ]
