"""
Domain Scraper Lambda — Configurable domain-specific content scraper.

Uses SERP API to find links on configured
domains, then Tavily to extract content, and writes results to S3.

The domains and URL patterns are configurable via environment variables
or S3 config files — no source code changes needed to target new domains.

Environment variables:
    SCRAPER_DOMAINS_S3_URI  - S3 URI for domain config JSON (domains + URL patterns)
    CONTENT_STORE_BUCKET    - S3 bucket to write results to
    PAGINATION_SERP         - Number of SERP pages to traverse per domain
    LINKS_BATCH_SIZE        - Batch size for Tavily extraction
    INGESTION_PIPELINE_NAME - Prefix for output filenames
    API_KEYS_SECRET_ARN     - Secrets Manager ARN for SERPAPI_KEY and TAVILYAPI_KEY
"""

from serpapi import Client
from tavily import TavilyClient
import os
from datetime import datetime, timezone, timedelta
import boto3
from botocore.config import Config
import json
import re
from urllib.parse import urlparse
import time
from dateutil.relativedelta import relativedelta
from dateutil import parser

timeout_config = Config(read_timeout=300)

_secrets_cache = {}
def get_secret(key):
    if not _secrets_cache:
        client = boto3.client('secretsmanager', config=timeout_config)
        secret_arn = os.environ.get('API_KEYS_SECRET_ARN')
        response = client.get_secret_value(SecretId=secret_arn)
        _secrets_cache.update(json.loads(response['SecretString']))
    return _secrets_cache[key]


s3_client = boto3.client('s3', config=timeout_config)
sts = boto3.client('sts', config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()['Account']

serp_api_key = get_secret("SERPAPI_KEY")
tavily_api_key = get_secret("TAVILYAPI_KEY")


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

    return start.strftime('%-m/%-d/%Y'), end.strftime('%-m/%-d/%Y')


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
            return None
    else:
        try:
            return datetime.strptime(date_str, "%b %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            return None


def get_batch_links(links, batch_size):
    batch_size = int(batch_size)
    batched_links = []
    for i in range(0, len(links), batch_size):
        batch = links[i:i+batch_size]
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
        failed = response.get('failed_results', [])
        if failed:
            print(f"Tavily failed to extract {len(failed)} URLs: {failed}")
    return all_response


# ─── Domain & Pattern Configuration ────────────────────────────────────────────

def get_scraper_config():
    """
    Load scraper configuration from S3.
    
    Expected config format:
    {
        "domains": ["techcrunch.com", "reuters.com/business"],
        "url_patterns": [
            {"inurl": "/article/", "exclude": "/tag/"},
            {"inurl": "/news/", "exclude": "/category/"}
        ],
        "excluded_domains": ["forms.google.com"],
        "excluded_paths": ["forum", "board", "login"]
    }
    
    If no S3 config is set, falls back to a simple domain list.
    """
    config_s3_uri = os.environ.get('SCRAPER_DOMAINS_S3_URI')

    if not config_s3_uri:
        # Fallback: just use SERP without URL patterns (simpler scraping)
        return {
            "domains": [],
            "url_patterns": [{"inurl": "", "exclude": ""}],
            "excluded_domains": ["forms.google.com", "forms.gle"],
            "excluded_paths": ["forum", "board", "login", "signup"]
        }

    try:
        s3_path = config_s3_uri.replace('s3://', '', 1)
        bucket_name, _, file_key = s3_path.partition('/')
        response = s3_client.get_object(Bucket=bucket_name, Key=file_key, ExpectedBucketOwner=ACCOUNT_ID)
        file_content = response['Body'].read().decode('utf-8')
        config = json.loads(file_content)
        print(f"Loaded scraper config: {len(config.get('domains', []))} domains, {len(config.get('url_patterns', []))} patterns")
        return config
    except Exception as e:
        print(f"Error loading scraper config from S3: {str(e)}")
        raise


# ─── SERP Search ────────────────────────────────────────────────────────────────

def search_serp(client, domain, query, pattern, page, start, end, all_links):
    """Search SERP for links on a specific domain."""
    inurl = pattern.get("inurl", "")
    exclude = pattern.get("exclude", "")

    q = f"site:{domain} {query}"
    if inurl:
        q = f"site:{domain} inurl:{inurl} {query}"
    if exclude:
        q += f" -inurl:{exclude}"

    params = {
        "engine": "google",
        "q": q,
        "start": page * 10,
        "tbs": f"cdr:1,cd_min:{start},cd_max:{end}"
    }

    result = client.search(params)
    print(f"Searching: {domain} | pattern:{inurl} | query:{query} | Page {page+1}")

    organic_results = result.get("organic_results", [])
    if not organic_results:
        return False

    for item in organic_results:
        link = item.get("link")
        if link and link not in all_links:
            raw_date = item.get("date")
            all_links[link] = {
                "date": resolve_date(raw_date),
                "pattern": inurl
            }

    return True


def get_url_serp(domains, queries, pagination, start, end, url_patterns):
    """Get URLs via SERP search across all domains and patterns."""
    client = Client(api_key=serp_api_key)
    all_links = {}
    pagination = int(pagination)

    if isinstance(queries, str):
        queries = [queries]

    for domain in domains:
        for query in queries:
            for pattern in url_patterns:
                try:
                    for page in range(pagination):
                        has_results = search_serp(client, domain, query, pattern, page, start, end, all_links)
                        if not has_results:
                            break
                        time.sleep(1)  # nosemgrep: arbitrary-sleep  # intentional rate-limiting between API calls
                except Exception as e:
                    print(f"Error: {domain} | {query} | {pattern.get('inurl', '')}: {str(e)}")

    print(f"Total unique links found: {len(all_links)}")
    return all_links


# ─── Content Extraction & Filtering ────────────────────────────────────────────

def extract_and_filter_links(results_tavily, links, config):
    """Extract article links from Tavily results and filter out excluded domains/paths."""
    excluded_domains = config.get("excluded_domains", [])
    excluded_paths = config.get("excluded_paths", [])
    valid_links = []
    article_date_map = {}
    markdown_link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'

    for result in results_tavily:
        source_url = result.get('url')
        source_date = links.get(source_url, {}).get('date') if isinstance(links.get(source_url), dict) else links.get(source_url)
        raw_content = result.get('raw_content', '')
        matches = re.findall(markdown_link_pattern, raw_content)

        for link_text, url in matches:
            if not url.startswith('https://'):
                continue
            try:
                parsed_url = urlparse(url)
                if any(excluded in parsed_url.netloc for excluded in excluded_domains):
                    continue
                if any(excluded in parsed_url.path.lower() for excluded in excluded_paths):
                    continue

                valid_links.append(url)
                article_date_map[url] = source_date
            except Exception as e:
                print(f"Error parsing {url}: {e}")
                continue

    return valid_links, article_date_map


# ─── S3 Writer ──────────────────────────────────────────────────────────────────

def add_to_json(query, results, output_bucket, output_folder, links_meta, from_date):
    try:
        processname = os.environ.get('INGESTION_PIPELINE_NAME', 'domain_scraper')
        s3_uris = []
        for result in results:
            timestamp = generate_timestamp()
            json_obj = {
                "url": result['url'],
                "research_topic": query,
                "content": result['raw_content'],
                "published_date": links_meta.get(result['url']),
                "created_at": timestamp,
                "news_from_date": from_date
            }

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
        print(f"Error in add_to_json: {str(e)}")
        raise


# ─── Lambda Handler ─────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    try:
        queries = event.get('search_terms', [])
        data_folder = event.get("prefix")
        output_bucket = event.get("content_store_bucket")
        pagination = os.environ.get("PAGINATION_SERP", "1")
        batch_size = os.environ.get("LINKS_BATCH_SIZE", "20")

        if not queries or not data_folder or not output_bucket:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing search_terms or prefix in the event'})
            }

        # Load scraper configuration
        config = get_scraper_config()
        domains = config.get("domains", [])
        url_patterns = config.get("url_patterns", [{"inurl": "", "exclude": ""}])

        if not domains:
            print("No domains configured in scraper config — skipping domain scraper")
            return {'total_files': 0}

        # Get date range
        request_type = event.get("type")
        frequency = event.get("frequency")
        from_date = event.get("from_date")
        day_of_month = event.get("day_of_month")

        start, end = get_date_range(request_type, frequency, from_date, day_of_month)

        # Step 1: SERP search to find links on target domains
        all_links = get_url_serp(domains, queries, pagination, start, end, url_patterns)

        if not all_links:
            print("No links found from SERP search")
            return {'total_files': 0}

        # Step 2: Extract content from found links using Tavily
        link_urls = list(all_links.keys())
        batched_links = get_batch_links(link_urls, batch_size)
        results_tavily = tavily_search(batched_links)

        if not results_tavily:
            print("No content extracted from links")
            return {'total_files': 0}

        # Step 3: (Optional) Extract nested article links from scraped pages
        # This is useful for aggregator sites that link to individual articles
        nested_links, article_date_map = extract_and_filter_links(results_tavily, all_links, config)

        # Step 4: If nested links found, extract their content too
        final_results = results_tavily  # Default: use direct scrape results
        final_meta = {r['url']: all_links.get(r['url'], {}).get('date') if isinstance(all_links.get(r['url']), dict) else all_links.get(r['url']) for r in results_tavily}

        if nested_links:
            print(f"Found {len(nested_links)} nested article links — extracting content")
            nested_batched = get_batch_links(nested_links, batch_size)
            nested_results = tavily_search(nested_batched)
            if nested_results:
                final_results = nested_results
                final_meta = article_date_map

        # Step 5: Write results to S3
        from_date_formatted = ""
        if from_date:
            try:
                from_date_formatted = parser.parse(from_date).strftime("%Y-%m-%d")
            except Exception:
                from_date_formatted = from_date

        search_query_label = ', '.join(queries) if isinstance(queries, list) else queries
        write_result = add_to_json(search_query_label, final_results, output_bucket, data_folder, final_meta, from_date_formatted)

        return {'total_files': write_result.get('total_files', 0)}

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
