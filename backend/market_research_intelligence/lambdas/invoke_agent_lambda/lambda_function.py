import boto3
import json
import os
from datetime import datetime, timezone
import uuid

from botocore.config import Config

timeout_config = Config(read_timeout=300)
bedrock_config = Config(
    read_timeout=300,     
    connect_timeout=20,
    retries={'total_max_attempts': 2, 'mode': 'standard'}
)

s3_retry_config = Config(
    read_timeout=300,
    retries={'total_max_attempts': 4, 'mode': 'standard'}
)

bedrock_client = boto3.client('bedrock-agentcore', region_name=os.environ.get('AWS_REGION', 'us-east-1'), config=bedrock_config) 
s3_client = boto3.client('s3', config=s3_retry_config)
sts = boto3.client('sts', config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()['Account']



def generate_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")

def add_to_json(item,output_s3_key,output_bucket):
    try:
        # timestamp = generate_timestamp()
        # file_name = f"{timestamp}.json"
        # output_s3_key = f"{output_folder}/{file_name}"
            
        s3_client.put_object(
            Bucket=output_bucket,
            Key=output_s3_key,
            Body=json.dumps(item).encode('utf-8'),
            ContentType='application/json',
            ExpectedBucketOwner=ACCOUNT_ID  
        )
        
        print(f"Successfully wrote to S3 bucket--{output_bucket}, key -- {output_s3_key}")
        output_s3_uri = f"s3://{output_bucket}/{output_s3_key}"
            
        return {
            'output_s3_uri': output_s3_uri
        }
    except Exception as e:
        print(f"Error creating JSON: {str(e)}")
        raise

def read_s3_json(s3_uri):
    # Remove 's3://' and split bucket/key
    s3_uri = s3_uri.replace("s3://", "")
    bucket, key = s3_uri.split("/", 1)
    
    # Get object from S3
    response = s3_client.get_object(Bucket=bucket, Key=key, ExpectedBucketOwner=ACCOUNT_ID)
    
    # Read and convert to dict
    content = response["Body"].read().decode("utf-8")
    data = json.loads(content)
    return data, key

def lambda_handler(event, context):

    print("Received event: ",event)

    mode= event.get("mode", "full")

    if mode == 'full':
        customer = event.get('customer')
        if not customer:
            raise ValueError("Customer name is required")
        s3_uri = event.get('input_s3_uri')
        data, key =read_s3_json(s3_uri)
        trace_s3_uri=s3_uri
        urls=[]
        contents=[]
        published_date = [] 
        research_topic = data[0].get('research_topic', data[0].get('research_topic', ''))
        category = data[0]['category']
        for item in data:
            contents.append(item["content"])
            urls.append(item["url"])
            published_date.append(item["published_date"]) 
            news_from_date = item["news_from_date"]
        payload=json.dumps({"research_topic": research_topic, "category": category, "s3_object_key": key, "client": customer, "mode":"full" }) 
        timestamp = generate_timestamp()
        file_name = f"{timestamp}.json"
        # key is like: prefix/.../category/filename.json — strip filename, keep prefix+category
        base_path = key.rsplit("/", 1)[0] if "/" in key else key
        output_s3_key = f"{base_path}/{file_name}" 
    
    
    elif mode == 'regenerate':
        s3_uri = event.get('s3_uri')
        data, input_key = read_s3_json(s3_uri)
        user_instruction=event["regenerate"]["user_instruction"]
        field = event["regenerate"]["field"]
        research_topic=data.get('research_topic', data.get('research_topic', ''))
        category=data['category']
        customer = data['customer']
        content_s3_uri= data['trace_s3_uri']
        trace_s3_uri=content_s3_uri
        content_data, key = read_s3_json(content_s3_uri)
        urls=[]
        published_date = []
        for item in content_data:
            urls.append(item["url"])
            published_date.append(item["published_date"])
            news_from_date = item["news_from_date"]
        payload=json.dumps({"research_topic": research_topic, "category": category, "s3_object_key": key, "client": customer, "mode": "regenerate",
        "regenerate":{"field":field, "user_instruction":user_instruction,
        "existing_output":{"summary":data['summary'],"insights":data['insights'],
        "implications":data['implications'],"title":data['title'],"keywords":data['keywords']}}})
        output_s3_key = input_key


    elif mode == 'insights-implications':
        s3_uri = event.get('s3_uri')
        data, input_key = read_s3_json(s3_uri)
        research_topic=data.get('research_topic', data.get('research_topic', ''))
        category=data['category']
        customer = data['customer']
        content_s3_uri= data['trace_s3_uri']
        trace_s3_uri=content_s3_uri
        content_data, key = read_s3_json(content_s3_uri)
        urls=[]
        published_date = []
        for item in content_data:
            urls.append(item["url"])
            published_date.append(item["published_date"])
            news_from_date = item["news_from_date"]
        payload=json.dumps({"research_topic": research_topic, "category": category, "s3_object_key": key, "client": customer, "mode": "insights-implications",
        "regenerate":{"existing_output":{"summary":data['summary'],"title":data['title'],"keywords":data['keywords']}}})
        output_s3_key = input_key


    response = bedrock_client.invoke_agent_runtime(
        agentRuntimeArn=os.environ['AGENT_RUNTIME_ARN'],
        runtimeSessionId=str(uuid.uuid4()),
        payload=payload
    ) 

    # citation_string = ", ".join(urls)
    print("agent response is -> ",response) 
    response_body = response['response'].read()
    agent_result_raw = json.loads(response_body)
    print("Agent Response:", agent_result_raw)
    print("Agent Response Type:", type(agent_result_raw))

    timestamp = datetime.now().strftime("%Y-%m-%d")

    while isinstance(agent_result_raw, str):
        agent_result_raw = json.loads(agent_result_raw)
    
    print("Agent Response (after type conversion): ", type(agent_result_raw), " --> " ,agent_result_raw)  

    # Deterministic mode-based field enforcement — override any LLM hallucination
    if mode == "full":
        agent_result_raw["insights"] = ""
        agent_result_raw["implications"] = ""

    result = research_topic[0] if isinstance(research_topic, list) else research_topic

    result_data = {
        **agent_result_raw,
        "research_topic": research_topic,
        "research_topic": research_topic,
        "category": category,
        "trace_s3_uri": trace_s3_uri,
        "citation": urls,
        "customer": customer,
        "published_date": published_date,
        "news_from_date": news_from_date,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    }

    
    result_bucket= os.environ.get('RESULTS_BUCKET')
    write=add_to_json(result_data, output_s3_key,result_bucket)
    

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Agent executed successfully',
            'output_s3_uri': write['output_s3_uri']
        })
    }
