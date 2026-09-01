from serpapi import Client
from tavily import TavilyClient
import os
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
import boto3
from botocore.config import Config
import json
import time
import calendar
from dateutil import parser

timeout_config = Config(read_timeout=300)


_secrets_cache = {}
def get_secret(key):
    if not _secrets_cache:
        client = boto3.client('secretsmanager', config=timeout_config)
        secret = client.get_secret_value(SecretId=os.environ['API_KEYS_SECRET_NAME'])
        _secrets_cache.update(json.loads(secret['SecretString']))
    return _secrets_cache[key]



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


s3_client = boto3.client('s3', config=timeout_config)
sts = boto3.client('sts', config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()['Account']
serp_api_key = get_secret("SERPAPI_KEY")
tavily_api_key = get_secret("TAVILYAPI_KEY")

def generate_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")

def resolve_date(date_str):  
    if not date_str:
        return None
    if "ago" in date_str:
        parts = date_str.split()
        value = int(parts[0])
        unit = parts[1]
        now = datetime.now(timezone.utc)
        if "hour" in unit:
            return (now - timedelta(hours=value)).strftime("%Y-%m-%d")
        elif "day" in unit:
            return (now - timedelta(days=value)).strftime("%Y-%m-%d")
        elif "week" in unit:
            return (now - timedelta(weeks=value)).strftime("%Y-%m-%d")
        else:
            print((f"Unhandled relative date format: {date_str}"))
            return None
    else:
        try:
            return datetime.strptime(date_str, "%b %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            return None

def get_batch_links(links, batch_size):
    batched_links=[]
    batch_size = int(batch_size)
    for i in range(0,len(links),batch_size):
        batch=links[i:i+batch_size]
        batched_links.append(batch)
    return batched_links


def tavily_search(batched_links):
    all_response = []
    client = TavilyClient(tavily_api_key)
    for batch in batched_links: 
        response = client.extract(
            urls=batch, 
            extract_depth="advanced"
        )
        all_response.extend(response.get('results', []))
    return all_response



def search_serp(client, domain, research_topic, page, start, end, all_links):
    """Retrieving the links from the serp api and storing it in all_links {}"""
    params = {
        "engine": "google",
        "q": f"site:{domain} {research_topic}",
        "start": page * 10,
        "tbs": f"cdr:1,cd_min:{start},cd_max:{end}"
    }

    result = client.search(params)
    print(f"Searching on domain {domain} with research_topic {research_topic} at page {page+1}")
    organic_results = result.get("organic_results", [])

    if not organic_results:
        print(f"No results for {domain} with research_topic {research_topic} at page {page+1} so breaking the loop")
        return False

    print(f"Found {len(organic_results)} results for {domain} - {research_topic} page {page+1}")

    for item in organic_results:
        link = item.get("link")
        if link and link not in all_links:
            raw_date = item.get("date")
            all_links[link] = resolve_date(raw_date)

    return True


def pagination_serp(client, domain, research_topic, pagination, start, end, all_links):
    """Helper fn to search on serp"""
    try:
        for page in range(pagination):
            is_pages = search_serp(client, domain, research_topic, page, start, end, all_links) ##helper function to call serp api based on pagination
            if not is_pages:
                break
            time.sleep(1)  # nosemgrep: arbitrary-sleep  # intentional rate-limiting between API calls
    except Exception as e:
        print(f"Error: {domain} - {research_topic}: {str(e)}")


def get_url_serp(domains, search_terms, pagination, category_str, start, end):
    """Getting the urls from the serp api with helper fuctions -- this function act as a main function for the serp api calls"""
    client = Client(api_key=serp_api_key)
    all_links = {}
    pagination = int(pagination)

    for domain in domains:
        print(f"Searching on domain {domain}")
        for research_topic in search_terms:
            query = research_topic + category_str
            print(f"Searching for {query} on domain {domain}")
            pagination_serp(client, domain, query, pagination, start, end, all_links)   ##helper functions to search based on pagination

    print(f"Total unique links: {len(all_links)} and the link are \n {all_links}")
    return all_links


def get_domains():
    try:
        domain_s3_uri = os.environ.get('PRESS_RELEASE_CONFIG_S3_URI')
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



def add_to_json(query, results, output_bucket, output_folder, links_meta, from_date): 
    try:
        processname = os.environ.get('INGESTION_PIPELINE_NAME')
        s3_uris=[]
        for result in results:
            timestamp = generate_timestamp()
            json_obj = {
                "url": result['url'],
                "research_topic": query,
                "content": result['raw_content'],
                "published_date": links_meta.get(result['url']),
                "created_at": timestamp,
                "news_from_date":from_date
            }
            
            file_name = f"{processname}_{timestamp}.json" 
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



def lambda_handler(event,context):
    try:
        search_terms = event.get('search_terms', [])
        domains=get_domains()
        print(f"The domains are {domains}")
        data_folder=event.get("prefix")
        output_bucket = event.get("content_store_bucket")
        batch_size=os.environ.get('LINKS_BATCH_SIZE')
        pagination_serp=os.environ.get('PAGINATION_SERP')
        category = event.get("category", [])
        if not search_terms or not data_folder:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing search_terms or prefix in the event'
                })
            }
        if not output_bucket or not batch_size:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing ENV params'
                })
            }
        if category:
            category_str = " " + " OR ".join(category) 
        else:
            category_str= ""



        request_type = event.get("type")
        frequency     = event.get("frequency")
        from_date     = event.get("from_date")
        day_of_month  = event.get("day_of_month")

        start,end=get_date_range(request_type,frequency,from_date,day_of_month)

        links = get_url_serp(domains, search_terms, pagination_serp, category_str,start,end)
        print(f"The respective links to get content are: \n {links}")
        batched_list=get_batch_links(list(links.keys()), batch_size)
        print(f"The links after putting onto batches are: \n {batched_list}")
        results = tavily_search(batched_list)
        print(f"The result came is \n {results}")

        from_date_formatted = ""
        if from_date:
            try:
                from_date_formatted = parser.parse(from_date).strftime("%Y-%m-%d")
            except Exception:
                from_date_formatted = from_date

        search_query_to_add = ', '.join(search_terms)
        write_result = add_to_json(search_query_to_add, results, output_bucket, data_folder, links, from_date_formatted)
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
