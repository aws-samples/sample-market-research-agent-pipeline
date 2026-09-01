import json
import os
import uuid
import boto3
from botocore.config import Config
from perplexity import Perplexity
from datetime import datetime, timezone, timedelta
import calendar
from dateutil.relativedelta import relativedelta
from dateutil import parser

timeout_config = Config(read_timeout=300)


_secrets_cache = {}
def get_secret(key):
    if not _secrets_cache:
        client = boto3.client('secretsmanager', config=timeout_config)
        secret = client.get_secret_value(SecretId=os.environ['API_KEYS_SECRET_NAME'])
        _secrets_cache.update(json.loads(secret['SecretString']))
    return _secrets_cache[key]

s3_client = boto3.client('s3', config=timeout_config)
sts = boto3.client('sts', config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()['Account']



def get_date_range(request_type,frequency,from_date,day_of_month):

    today = datetime.now().date()
    end = today

    
    # Case 1: On-Demand 
    if request_type == "on-demand":
        if not from_date:
            raise ValueError("on-demand payload must include 'from_date'")
        start = datetime.strptime(from_date, "%m/%d/%Y").date()

    # ── Case :Scheduler ─────────────────────────────────────────────
    elif request_type == "scheduler":

        # Case: Daily -------> start = yesterday
        if frequency == "daily":
            start = end - timedelta(days=1)

        # Case: Weekly -------> start = 7 days before today
        elif frequency == "weekly":
            start = end - timedelta(weeks=1)

        # Case: Monthly -------> start = that day_of_month in the previous month
        elif frequency == "monthly":
            if not day_of_month:
                raise ValueError("monthly frequency requires 'day_of_month'")

            start = end - relativedelta(months=1)

            # Clamp day_of_month to the last valid day of that month
            # last_day = calendar.monthrange(one_month_ago.year, one_month_ago.month)[1]
            # clamped_day = min(int(day_of_month), last_day)

            # start = one_month_ago.replace(day=clamped_day)
        else:
            raise ValueError(f"Unknown frequency: '{frequency}'")
    else:
        raise ValueError(f"Unknown type: '{request_type}'")
    print(f"The start date is {start} and end date is {end}")
    return start.strftime('%-m/%-d/%Y'), end.strftime('%-m/%-d/%Y')



def generate_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
def search_api(queries,domains,max_res,max_tokens, api_key, start, end):
    client=Perplexity(api_key=api_key)
    search = client.search.create(
    query=f"Retrieve the results from dates {str(start)} to {str(end)} based on these keywords {queries}",
    search_domain_filter=domains,
    max_results=max_res,
    max_tokens_per_page=max_tokens,
    search_after_date_filter = str(start)
    )
    results=[]
    for result in search.results:
        print(f"{result.title}: {result.url}")
        results.append({
            "title":result.title,
            "url":result.url,
            "snippet": result.snippet,
            "published_date": result.date
        })
    return results


def get_domains():
    try:
        domain_s3_uri = os.environ.get('DOMAINS_CONFIG_S3_URI')
        if not domain_s3_uri:
            raise ValueError("Domains S3 URI is not present in env")
        s3_path = domain_s3_uri.replace('s3://', '', 1)
        bucket_name, sep, file_key = s3_path.partition('/')
        print(f"bucket_name is {bucket_name}, file_key is {file_key}")
        if not bucket_name or not file_key:
            raise ValueError("Invalid S3 URI- Bucket name ot file key could not be found")
        response = s3_client.get_object(Bucket=bucket_name, Key=file_key, ExpectedBucketOwner=ACCOUNT_ID)
        file_content = response['Body'].read().decode('utf-8')
        data = json.loads(file_content)
        domains = data['domains']
        print(f"Recieved {len(domains)} domains from s3")
        return domains     
    except Exception as e:
        print(f"Error retrieving domains from S3: {str(e)}")
        raise  
def add_to_json(query, results, output_bucket, output_folder, from_date):
    try:
        s3_uris=[]
        for result in results:
            timestamp = generate_timestamp()
            json_obj = {
                "url": result['url'],
                "research_topic": query,
                "content": result['snippet'],
                "created_at": timestamp,
                "published_date": result['published_date'],
                "news_from_date":from_date
            }
            
            file_name = f"sonarsearch_{timestamp}.json" 
            print(f"Writing results to S3 bucket: {output_bucket}, folder_name: {output_folder}, file name: {file_name}")
            output_s3_key=f"{output_folder}/{file_name}"
            try:
                s3_client.put_object(
                    Bucket=output_bucket,
                    Key=output_s3_key,
                    Body=json.dumps(json_obj).encode('utf-8'),
                    ContentType='application/json',
                    ExpectedBucketOwner=ACCOUNT_ID
                )
                print(f"Successfully wrote JSON to {output_bucket}")
                output_s3_uri = f"s3://{output_bucket}/{output_folder}/{file_name}"
                s3_uris.append(output_s3_uri)
            except Exception as e:
                print(f"Error writing JSON to S3: {str(e)}")
                raise
        return{
                's3_uris': s3_uris,
                'total_files': len(s3_uris)
            }
    except Exception as e:
        print(f"Error creating JSON: {str(e)}")
        raise   
      
def lambda_handler(event, context):
    try:
        queries = event.get('search_terms', [])
        domains=get_domains()
        data_folder=event.get("prefix")
        try:
            api_key = get_secret("PERPLEXITY_API_KEY")
            print(f"✓ API key retrieved successfully (length: {len(api_key)})")
        except Exception as e:
            print(f"✗ Failed to retrieve API key: {str(e)}")
            raise
        timestamp=event.get("timestamp")
        output_bucket = event.get("content_store_bucket")  
        max_res = os.environ.get('MAX_RESULTS')
        category = event.get('category', '')
        
        max_tokens = os.environ.get('MAX_TOKENS_PER_PAGE')
        print(f"max result is {max_res} max token is {max_tokens}")
        if not queries:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing search_terms'
                })
            }
        if not output_bucket or not max_res or not max_tokens:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing ENV params'
                })
            }
        search_query = ', '.join(queries)
        if category:
            category_str = ", ".join(category)
            search_query = f"{search_query} of category, {category_str}"
        print(f"Final search query is: {search_query}")

        request_type = event.get("type")
        frequency     = event.get("frequency")
        from_date     = event.get("from_date")
        day_of_month  = event.get("day_of_month")

        start,end=get_date_range(request_type,frequency,from_date,day_of_month)
        
        results = search_api(search_query, domains, max_res, max_tokens, api_key, start, end)
        print(f"The result came is \n {results}")

        from_date_formatted = ""
        if from_date:
            try:
                from_date_formatted = parser.parse(from_date).strftime("%Y-%m-%d")
            except Exception:
                from_date_formatted = from_date

        write_result = add_to_json(search_query, results, output_bucket, data_folder, from_date_formatted)
        return {
            'total_files': write_result.get('total_files',0)  
        } 
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }


