import boto3
import json
import os
import re
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

MODEL_ID = os.environ['MODEL_INFERENCE_PROFILE']

SYSTEM_PROMPT = """
You are a market research intelligence classification agent.

Input:
- research_topic: a market segment, industry, or competitive arena
- content: article or news text

Task:
Analyze the content in the context of the given research topic and determine whether it belongs to:
- competitive_landscape
- deals_and_partnerships
- Both competitive_landscape and deals_and_partnerships
- others (if the content does not substantively fit into either category)

Classification Guidelines:

Competitive Landscape:
- Product launches, updates, or discontinuations
- Market entry or exit by a company
- Pricing changes, positioning shifts, or go-to-market strategy changes
- Competitive benchmarking, market share data, or ranking changes
- Leadership changes, restructuring, or strategic pivots
- New capabilities, features, or technology announcements
- Expansion into new geographies or market segments
- Customer wins, losses, or major contract announcements
- Earnings, revenue, or growth metrics that signal competitive position

Deals & Partnerships:
- Mergers, acquisitions, or divestitures
- Licensing agreements or collaborations
- Co-development or co-marketing deals
- Research collaborations or joint ventures
- Distribution or commercialization agreements
- Technology transfer or IP licensing
- Strategic alliances or partnerships
- Funding rounds, investment deals, or venture capital
- Manufacturing, supply, or infrastructure agreements

Both competitive_landscape and deals_and_partnerships:
- Content that discusses both competitive positioning AND deal/partnership aspects
- Example: "Company X acquires Company Y, gaining dominant market share in cloud security"

Others:
- Content that does not substantively belong to either competitive_landscape or deals_and_partnerships
- General industry commentary, opinion pieces, or thought leadership without specific competitive or deal content
- Content that is NOT relevant to the given research topic. If the content discusses a completely unrelated market segment or industry, classify it as "others"


Rules:
- Use only the provided categories: "competitive_landscape", "deals_and_partnerships", "others".
- FIRST, check if the content is relevant to the given research topic. If the content is about a completely unrelated market or industry, return ["others"] immediately.
- If both competitive landscape AND deals/partnership aspects are substantively discussed, return ["competitive_landscape", "deals_and_partnerships"]
- If only competitive/strategic aspects are discussed, return ["competitive_landscape"]
- If only deal/partnership/M&A aspects are discussed, return ["deals_and_partnerships"]
- If the content does not clearly or substantively fit into either category, return ["others"]
- Focus on the PRIMARY content of the article - minor mentions don't qualify for inclusion
- Do not wrap the JSON in markdown or code blocks. Return raw JSON only.
- Do not include any additional text, explanations, or formatting outside the JSON.
- Respond ONLY with valid JSON in the following format:

{
  "category": ["..."]
}
"""


def lambda_handler(event, context):
    print("event is : ",event)
    
    source_bucket = event.get('bucket','')
    source_key = event.get('key','') 
    

    # Read JSON file
    response = s3.get_object(Bucket=source_bucket, Key=source_key, ExpectedBucketOwner=ACCOUNT_ID)
    json_content = response['Body'].read().decode('utf-8')

    record = json.loads(json_content) 
    from_date_raw = record.get("news_from_date", "")
    from_date_formatted = ""
    if from_date_raw:
        try:
            from dateutil import parser
            from_date_formatted = parser.parse(from_date_raw).strftime("%Y-%m-%d")
        except Exception:
            from_date_formatted = ""
    content = record.get('content', '') 
    research_topic = record.get("research_topic", "")

    user_prompt = f"""
Research Topic: {research_topic}

Content: {content}
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "temperature": 0,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    }

    parsed_output = invoke_and_parse_json(bedrock, MODEL_ID, body)
    print("parsed output is: ", parsed_output) 

    category = parsed_output.get("category", [])

    if (len(category) == 0 ):
        print("no category given by LLM so adding it under others category") 
        category.append("others")  

    return_list_of_prefixes = []
    for cat in category:
        
        if isinstance(record, str):
            record = json.loads(record)  
        record["category"] = cat 
        record["source_bucket"] = source_bucket
        record["source_key"] = source_key
        record["news_from_date"] = from_date_formatted
        
        prefix, filename = source_key.rsplit("/", 1)
        cat_key = f"{prefix}/{cat}/{filename}"

        record = json.dumps(record) 
        s3.put_object(
            Bucket=source_bucket,
            Key=cat_key,
            Body=record.encode("utf-8"),
            ExpectedBucketOwner=ACCOUNT_ID
        ) 

        return_list_of_prefixes.append(f"{prefix}/{cat}/")

    

    print("return_list_of_prefixes: ",return_list_of_prefixes) 
    
    return return_list_of_prefixes 


# def parse_s3_uri(s3_uri):
#     parsed = s3_uri.replace('s3://', '').split('/', 1)
#     bucket = parsed[0]
#     key = parsed[1]
#     return bucket, key  


def extract_json(text: str):
    text = text.strip()

    # Remove code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Extract first JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")

    return json.loads(match.group())


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
            contentType="application/json",
            accept="application/json",
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
