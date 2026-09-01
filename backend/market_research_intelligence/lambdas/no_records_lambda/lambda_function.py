import boto3
import json
import os
from datetime import datetime, timezone, timedelta
from botocore.config import Config

timeout_config = Config(read_timeout=300)

s3 = boto3.client("s3", config=timeout_config)
sts = boto3.client("sts", config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()["Account"]

IST = timezone(timedelta(hours=5, minutes=30))
RESULTS_BUCKET = os.environ["AGENT_RESULTS_BUCKET"]


def _extract_research_topic(search_terms, prefix):
    # Extract research_topic - prefer from search_terms list, fallback to parsing prefix
    if search_terms:
        return search_terms[0]
    
    # Prefix format -> "scheduled_prefix/research_topic_timestamp" or "research_topic_timestamp"
    # Extract the last path segment before the timestamp
    last_segment = prefix.rsplit("/", 1)[-1] if "/" in prefix else prefix
    # Split on '_' and take everything before the timestamp (YYYY-)
    parts = last_segment.split("_")
    research_topic_parts = []
    for part in parts:
        if len(part) >= 4 and part[:4].isdigit():
            break
        research_topic_parts.append(part)
    return " ".join(research_topic_parts) if research_topic_parts else ""

def _write_placeholder_files(prefix, json_body, bucket, account_id):
    # Write to both category folders so the UI picks them up
    error_response = None
    for category in ["competitive_landscape", "deals_and_partnerships"]:
        key = f"{prefix}/{category}/no_records.json"
        print(f"Writing no-records placeholder to s3://{bucket}/{key}")
        try:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=json_body.encode("utf-8"),
                ContentType="application/json",
                ExpectedBucketOwner=account_id
            )
        except Exception as e:
            print(f"Failed to write no-records placeholder to {key}: {e}")
            error_response = {"key": key, "error": str(e)}
            break
    return error_response


def lambda_handler(event, context):
    print("event is: ", event)

    prefix = event.get("prefix", "")
    search_terms = event.get("search_terms", [])
    from_date_raw = event.get("from_date", "")
    from_date = ""
    if from_date_raw:
        try:
            from dateutil import parser
            from_date = parser.parse(from_date_raw).strftime("%Y-%m-%d")
        except Exception:
            from_date = from_date_raw

    research_topic = _extract_research_topic(search_terms, prefix)

    no_records_json = {
        "summary": f"No records were found for the given research_topic '{research_topic}' since the requested time frame {from_date}" if from_date else f"No records were found for the given research_topic '{research_topic}'",
        "insights": "",
        "implications": "",
        "title": f"No records found for {research_topic}",
        "keywords": [],
        "research_topic": research_topic,
        "category": "",
        "trace_s3_uri": "",
        "citation": [],
        "customer": "",
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ"),
        "news_from_date": from_date,
        "published_date": [],
        "no_record_found": True
    }

    json_body = json.dumps(no_records_json)

    error_response = _write_placeholder_files(prefix, json_body, RESULTS_BUCKET, ACCOUNT_ID)
    if error_response:
        return {
            "status": "error",
            "prefix": prefix,
            "research_topic": research_topic,
            "message": f"ClientError while writing placeholder to {error_response['key']}: {error_response['error']}"
        }

    return {
        "status": "no_records",
        "prefix": prefix,
        "research_topic": research_topic,
        "message": f"No records found. Placeholder files written to {prefix}/clinical/ and {prefix}/partnership/"
    }