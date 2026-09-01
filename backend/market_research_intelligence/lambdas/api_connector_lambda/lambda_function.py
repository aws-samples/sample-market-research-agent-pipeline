"""
API Connector Lambda — Deal intelligence data fetcher.

Calls a Crunchbase-style deal intelligence API to fetch funding rounds,
M&A events, and company data. Also supports a generic REST connector
for any structured API endpoint.

Environment variables:
    DATA_SOURCE_API_URL     - The API endpoint to call
    DATA_SOURCE_TYPE        - Type of API for response parsing ("crunchbase" or "generic")
    CONTENT_STORE_BUCKET    - S3 bucket to write results to
    INGESTION_PIPELINE_NAME - Prefix for output filenames
    
    # Crunchbase-specific config (fetched from Secrets Manager):
    API_KEYS_SECRET_NAME    - Secrets Manager ARN containing CRUNCHBASE_USER_KEY
    PAGESIZE                - Results per page (default 25)
    MAX_PAGES               - Max pages to fetch (default 5)
"""

import json
import requests
import os
import boto3
from botocore.config import Config
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from dateutil import parser

# --- Secrets Manager helper (same pattern as other lambdas) ---
_secrets_cache = {}
def get_secret(key):
    if not _secrets_cache:
        client = boto3.client('secretsmanager', config=Config(read_timeout=300))
        secret_arn = os.environ.get('API_KEYS_SECRET_NAME')
        if not secret_arn:
            raise ValueError("API_KEYS_SECRET_NAME env var not set")
        response = client.get_secret_value(SecretId=secret_arn)
        _secrets_cache.update(json.loads(response['SecretString']))
    return _secrets_cache.get(key, "")


timeout_config = Config(read_timeout=300)
s3_client = boto3.client('s3', config=timeout_config)

sts = boto3.client('sts', config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()['Account']


def generate_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")


def get_date_range(request_type, frequency, from_date, day_of_month):
    today = datetime.now().date()
    end = today

    if request_type == "on-demand":
        if not from_date:
            raise ValueError("on-demand payload must include 'from_date'")
        start = datetime.strptime(from_date, "%m/%d/%Y").date()

    elif request_type == "scheduler":
        if frequency == "daily":
            start = end - timedelta(days=1)
        elif frequency == "weekly":
            start = end - timedelta(weeks=1)
        elif frequency == "monthly":
            if not day_of_month:
                raise ValueError("monthly frequency requires 'day_of_month'")
            start = end - relativedelta(months=1)
        else:
            raise ValueError(f"Unknown frequency: '{frequency}'")
    else:
        raise ValueError(f"Unknown type: '{request_type}'")

    print(f"Date range: {start} to {end}")
    return start.strftime('%-m/%-d/%Y'), end.strftime('%-m/%-d/%Y')


# ─── API Fetchers ───────────────────────────────────────────────────────────────

def fetch_crunchbase(query, start, end, page_size, max_pages):
    """
    Fetch from Crunchbase-style deal intelligence API.

    Returns funding rounds, acquisitions, and company events
    matching the query within the date range.
    """
    url = os.environ.get("DATA_SOURCE_API_URL")
    page_size = int(page_size)
    all_results = []
    page_count = 0

    fetch_all = str(max_pages).lower() in ['all', 'max']
    limit = 0 if fetch_all else int(max_pages)

    while True:
        if not fetch_all and page_count >= limit:
            break

        # Build the request body per Crunchbase Search API spec
        # query is an array of predicate objects, NOT a free-text string
        query_predicates = [
            {
                "type": "predicate",
                "field_id": "facet_ids",
                "operator_id": "includes",
                "values": ["company"]
            }
        ]

        # Add category/keyword filter if query provided
        if query:
            query_predicates.append({
                "type": "predicate",
                "field_id": "short_description",
                "operator_id": "contains",
                "values": [query]
            })

        # Add date range filter (last_funding_date or founded_on)
        if start:
            query_predicates.append({
                "type": "predicate",
                "field_id": "last_funding_at",
                "operator_id": "gte",
                "values": [start]
            })

        body = {
            "field_ids": [
                "identifier", "short_description", "categories",
                "funding_total", "last_funding_type", "founded_on",
                "num_employees_enum", "website_url", "rank_org_company"
            ],
            "query": query_predicates,
            "order": [{"field_id": "rank_org_company", "sort": "asc"}],
            "limit": page_size,
        }

        # Pagination via after_id
        if all_results:
            last_uuid = all_results[-1].get("uuid", all_results[-1].get("identifier", {}).get("uuid"))
            if last_uuid:
                body["after_id"] = last_uuid

        # Auth: Crunchbase uses user_key as a query parameter
        user_key = get_secret("CRUNCHBASE_USER_KEY")
        request_url = f"{url}?user_key={user_key}"

        try:
            print(f"Fetching page {page_count + 1} from deal intelligence API...")
            response = requests.post(request_url, json=body, headers={"Content-Type": "application/json"}, timeout=30)
            response.raise_for_status()
            data = response.json()

            entities = data.get("entities", data.get("results", data.get("items", [])))
            all_results.extend(entities)
            print(f"Fetched {len(entities)} entities from page {page_count + 1}")

            # No more results
            if len(entities) < page_size:
                break

        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            break

        page_count += 1

    return all_results


def fetch_generic_api(query, start, end, page_size, max_pages):
    """
    Generic API fetcher — calls a REST endpoint with configurable parameters.
    Expects the API to return JSON with a "results", "data", or "items" list.
    """
    url = os.environ.get("DATA_SOURCE_API_URL")
    page_size = int(page_size)
    max_pages = int(max_pages)
    all_results = []

    for page in range(max_pages):
        params = {
            "query": query,
            "start_date": start,
            "end_date": end,
            "page_size": page_size,
            "page": page + 1
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", data.get("data", data.get("items", [])))
            all_results.extend(results)
            print(f"Fetched {len(results)} items from page {page + 1}")

            if len(results) < page_size:
                break

        except requests.exceptions.RequestException as e:
            print(f"API request failed on page {page + 1}: {e}")
            break

    return all_results


# ─── Response Parsers ───────────────────────────────────────────────────────────

def parse_crunchbase_item(item, query, from_date):
    """Parse a Crunchbase-style entity into normalized format."""
    # Handle nested identifier structure
    identifier = item.get("identifier", item.get("properties", {}).get("identifier", {}))
    entity_id = identifier.get("permalink", identifier.get("uuid", ""))
    entity_name = identifier.get("value", item.get("name", item.get("title", "")))
    url = f"https://www.crunchbase.com/organization/{entity_id}" if entity_id else ""

    # Extract key financial data
    funding = item.get("funding_total", item.get("properties", {}).get("funding_total", {}))
    funding_value = funding.get("value_usd", funding.get("value", "")) if isinstance(funding, dict) else funding

    timestamp = generate_timestamp()
    return {
        "url": url,
        "research_topic": query,
        "content": json.dumps(item, default=str),
        "title": entity_name,
        "funding_total_usd": funding_value,
        "published_date": item.get("founded_on", item.get("created_at", item.get("updated_at", ""))),
        "created_at": timestamp,
        "news_from_date": from_date
    }


def parse_generic_item(item, query, from_date):
    """Parse a generic API result into normalized format."""
    timestamp = generate_timestamp()
    return {
        "url": item.get("url", item.get("link", "")),
        "research_topic": query,
        "content": item.get("content", item.get("description", item.get("summary", json.dumps(item, default=str)))),
        "title": item.get("title", item.get("name", "")),
        "published_date": item.get("published_date", item.get("date", item.get("created_at", ""))),
        "created_at": timestamp,
        "news_from_date": from_date
    }


# ─── S3 Writer ──────────────────────────────────────────────────────────────────

def write_results_to_s3(query, results, output_bucket, output_folder, parse_fn, from_date):
    """Write parsed results to S3 as individual JSON files."""
    try:
        processname = os.environ.get('INGESTION_PIPELINE_NAME', 'api_connector')
        s3_uris = []

        for item in results:
            json_obj = parse_fn(item, query, from_date)
            timestamp = generate_timestamp()
            file_name = f"{processname}_{timestamp}.json"
            output_s3_key = f"{output_folder}/{file_name}"

            try:
                s3_client.put_object(
                    Bucket=output_bucket,
                    Key=output_s3_key,
                    Body=json.dumps(json_obj).encode('utf-8'),
                    ContentType='application/json',
                    ExpectedBucketOwner=ACCOUNT_ID
                )
                s3_uris.append(f"s3://{output_bucket}/{output_s3_key}")
            except Exception as e:
                print(f"Error writing to S3: {str(e)}")
                raise

        return {'s3_uris': s3_uris, 'total_files': len(s3_uris)}
    except Exception as e:
        print(f"Error in write_results_to_s3: {str(e)}")
        raise


# ─── Lambda Handler ─────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    try:
        search_terms = event.get('search_terms', [])
        query = " OR ".join(search_terms) if isinstance(search_terms, list) else search_terms

        data_folder = event.get("prefix")
        output_bucket = event.get("content_store_bucket")
        data_source_type = os.environ.get("DATA_SOURCE_TYPE", "crunchbase")
        page_size = os.environ.get("PAGESIZE", "25")
        max_pages = os.environ.get("MAX_PAGES", "5")

        if not search_terms or not data_folder or not output_bucket:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing search_terms or prefix in the event'})
            }

        request_type = event.get("type")
        frequency = event.get("frequency")
        from_date = event.get("from_date")
        day_of_month = event.get("day_of_month")

        start, end = get_date_range(request_type, frequency, from_date, day_of_month)

        from_date_formatted = ""
        if from_date:
            try:
                from_date_formatted = parser.parse(from_date).strftime("%Y-%m-%d")
            except Exception:
                from_date_formatted = from_date

        # Route to the appropriate fetcher and parser
        if data_source_type == "crunchbase":
            results = fetch_crunchbase(query, start, end, page_size, max_pages)
            parse_fn = parse_crunchbase_item
        else:  # "generic"
            results = fetch_generic_api(query, start, end, page_size, max_pages)
            parse_fn = parse_generic_item

        print(f"Fetched {len(results)} results from {data_source_type} API")

        search_query_label = ', '.join(search_terms) if isinstance(search_terms, list) else search_terms
        write_result = write_results_to_s3(search_query_label, results, output_bucket, data_folder, parse_fn, from_date_formatted)

        return {'total_files': write_result.get('total_files', 0)}

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
