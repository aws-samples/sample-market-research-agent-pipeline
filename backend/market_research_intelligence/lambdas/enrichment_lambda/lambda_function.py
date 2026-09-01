from datetime import datetime, timezone, timedelta
import os
import boto3
from botocore.config import Config
import json

timeout_config = Config(read_timeout=300)
s3_client=boto3.client('s3', config=timeout_config)
sts = boto3.client('sts', config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()['Account']
def generate_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

def get_search_terms(bucket_name, file_key):
    try:
        print(f"bucket_name is {bucket_name}, file_key is {file_key}")
        if not bucket_name or not file_key:
            raise ValueError("Bucket name or file key could not be found")

        response = s3_client.get_object(Bucket=bucket_name, Key=file_key, ExpectedBucketOwner=ACCOUNT_ID)
        file_content = response['Body'].read().decode('utf-8')
        entry_words = json.loads(file_content)

        return [word.lower() for word in entry_words]
    except Exception as e:
        print(f"Error retrieving search_terms from S3: {str(e)}")
        raise     
def lambda_handler(event, context):
    timestamp=generate_timestamp()
    queries=event.get("research_topic", [])
    enrich_bucket = event.get("enrichment_bucket")
    enrich_file=event.get("enrichment_key")
    print(f"This is the research_topic from the event {queries}")
    content_store_bucket = os.environ["CONTENT_STORE_BUCKET"]
    search_terms = queries
    if enrich_bucket and enrich_file:
        entry_words=get_search_terms(enrich_bucket, enrich_file)
        search_terms = search_terms + entry_words
        
    from_date = event.get("from_date")
    if not from_date:
        frequency = event.get("frequency")
        today = datetime.now(timezone.utc)
        if frequency == "daily":
            from_date = (today - timedelta(days=1)).strftime("%m-%d-%Y")
        elif frequency == "weekly":
            from_date = (today - timedelta(days=7)).strftime("%m-%d-%Y")
        elif frequency == "monthly":
            from_date = (today - timedelta(days=30)).strftime("%m-%d-%Y")

    if event.get("type")=="scheduler":
        prefix = f"{event['prefix']}/{search_terms[0]}_{timestamp}"
    else:
        prefix = event['prefix']

    return {
        'search_terms': search_terms,
        'prefix': prefix,
        'content_store_bucket': content_store_bucket,
        'category': event.get("category"),
        'type': event.get("type"),
        'frequency': event.get("frequency"),
        'from_date': from_date,
        'day_of_week': event.get("day_of_week"),
        'day_of_month': event.get("day_of_month"),
    }