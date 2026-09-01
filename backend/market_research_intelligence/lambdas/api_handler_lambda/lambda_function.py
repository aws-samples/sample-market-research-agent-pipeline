import boto3
from botocore.config import Config
import json
import uuid
import os
from datetime import datetime, timezone, timedelta

timeout_config = Config(read_timeout=300)

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'POST,OPTIONS'
}

# EventBridge day-of-week: 1=Sun, 2=Mon, 3=Tue, 4=Wed, 5=Thu, 6=Fri, 7=Sat
DOW_NAMES = {
    '1': 'Sunday', '2': 'Monday', '3': 'Tuesday', '4': 'Wednesday',
    '5': 'Thursday', '6': 'Friday', '7': 'Saturday'
}

IST = timezone(timedelta(hours=5, minutes=30))

sts = boto3.client("sts", config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()["Account"]

def generate_scheduled_prefix(research_topic, frequency, schedule_day=None):
    """Generate a unique prefix like 'obesity_scheduled_weekly_wednesday_20260312T080000Z' for scheduled pipelines."""
    prefix_name = research_topic[0].lower().replace(' ', '_') if research_topic else 'unknown'
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
    
    base = f"{prefix_name}_scheduled_{frequency}"

    if frequency == 'weekly' and schedule_day:
        day_name = DOW_NAMES.get(str(schedule_day), str(schedule_day)).lower()
        return f"{base}_{day_name}_{timestamp}"
    elif frequency == 'monthly' and schedule_day:
        return f"{base}_{schedule_day}_{timestamp}"
    
    return f"{base}_{timestamp}"


def frequency_to_cron(frequency, schedule_time, schedule_day=None):
    """
    Convert frequency + time + optional day into an EventBridge Scheduler cron expression.
    
    Args:
        frequency: 'daily', 'weekly', or 'monthly'
        schedule_time: '09:00' (HH:MM in IST, since Scheduler handles timezone)
        schedule_day: For weekly: 1-7 (1=Sun, 2=Mon...7=Sat)
                      For monthly: 1-30 (day of month)
    
    Returns:
        cron expression string like 'cron(0 9 * * ? *)'
    """
    hour, minute = schedule_time.split(':')

    if frequency == 'daily':
        return f"cron({minute} {hour} * * ? *)"
    elif frequency == 'weekly':
        day = schedule_day or 2  # default Monday
        return f"cron({minute} {hour} ? * {day} *)"
    elif frequency == 'monthly':
        day = schedule_day or 1  # default 1st of month
        return f"cron({minute} {hour} {day} * ? *)"
    else:
        raise ValueError(f"Unknown frequency: {frequency}")


def frequency_to_human_readable(frequency, schedule_time, schedule_day=None):
    """Generate a human-readable schedule description."""
    if frequency == 'daily':
        return f"Every day at {schedule_time} IST"
    elif frequency == 'weekly':
        day_name = DOW_NAMES.get(str(schedule_day), 'Monday')
        return f"Every {day_name} at {schedule_time} IST"
    elif frequency == 'monthly':
        return f"Monthly on day {schedule_day or 1} at {schedule_time} IST"
    else:
        return f"Scheduled: {frequency}"


def handle_on_demand(body):
    """Handle on-demand project creation — start step function immediately."""
    client = boto3.client('stepfunctions', config=timeout_config)
    sf_arn = os.environ['SF_ARN']

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
    prefix = f"{body['research_topic'][0].lower().replace(' ', '_')}_{timestamp}"
    body["prefix"] = prefix

    s3_client = boto3.client('s3', config=timeout_config)
    results_bucket = os.environ['AGENT_RESULTS_BUCKET']

    s3_client.put_object(
        Bucket=results_bucket,
        Key=f"{prefix}/",
        Body=b'',
        Metadata={
            'type': 'on-demand'
        },
        ExpectedBucketOwner=ACCOUNT_ID
    )

    response = client.start_execution(
        stateMachineArn=sf_arn,
        name=f'execution-{uuid.uuid4()}',
        input=json.dumps(body)
    )

    return {
        'statusCode': 202,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'message': f'Started execution {response["executionArn"]}',
            'type': 'on-demand',
            'executionArn': response['executionArn'],
            'prefix': prefix
        })
    }


def handle_scheduled(body, prefix):
    """Handle scheduled project creation — create S3 folder + EventBridge Scheduler schedule."""
    frequency = body.get('frequency', '')
    schedule_time = body.get('time', '09:00')
    schedule_day = body.get('day_of_week') if frequency == 'weekly' else body.get('day_of_month')

    if frequency not in ('daily', 'weekly', 'monthly'):
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'frequency must be daily, weekly, or monthly'})
        }

    if frequency == 'weekly' and not schedule_day:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'schedule_day (1-7) is required for weekly frequency'})
        }

    if frequency == 'monthly' and not schedule_day:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'schedule_day (1-30) is required for monthly frequency'})
        }

    # Generate cron and human-readable schedule
    cron_expr = frequency_to_cron(frequency, schedule_time, schedule_day)
    human_schedule = frequency_to_human_readable(frequency, schedule_time, schedule_day)

    # 1) Create S3 marker object with metadata in agent results bucket
    s3_client = boto3.client('s3',config=timeout_config)
    results_bucket = os.environ['AGENT_RESULTS_BUCKET']

    s3_client.put_object(
        Bucket=results_bucket,
        Key=f"{prefix}/",
        Body=b'',
        Metadata={
            'type': 'scheduled',
            'scheduled_to_run_on': human_schedule
        },
        ExpectedBucketOwner=ACCOUNT_ID
    )

    # 2) Create EventBridge Scheduler schedule with IST timezone
    scheduler_client = boto3.client('scheduler',config=timeout_config)
    sf_arn = os.environ['SF_ARN']
    scheduler_role_arn = os.environ['SCHEDULER_ROLE_ARN']

    schedule_name = f"scheduled-{prefix}".replace('_', '-')[:64]

    # SF input = original body (without scheduler-specific fields) + prefix
    sf_input = {**body, 'prefix': prefix}

    scheduler_client.create_schedule(
        Name=schedule_name,
        ScheduleExpression=cron_expr,
        ScheduleExpressionTimezone='Asia/Kolkata',
        FlexibleTimeWindow={'Mode': 'OFF'},
        Target={
            'Arn': sf_arn,
            'RoleArn': scheduler_role_arn,
            'Input': json.dumps(sf_input)
        },
        Description=f"Scheduled pipeline for {prefix} - {human_schedule}",
        State='ENABLED'
    )

    # 3) Return meaningful response
    return {
        'statusCode': 201,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'message': f'Scheduled pipeline created: {human_schedule}',
            'prefix': prefix,
            'type': 'scheduler',
            'schedule_name': schedule_name,
            'schedule': human_schedule,
            'cron_expression': cron_expr
        })
    }


def lambda_handler(event, context):
    path = event.get('path', '')
    print(f'Request: {event}')
    print(f'Request path: {path}')
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': ''
        }
    
    if path == '/create-project':
        body = json.loads(event.get('body', '{}'))
        project_type = body.get('type', 'on-demand')

        if project_type == 'scheduler':
            research_topic = body.get('research_topic', [])
            frequency = body.get('frequency', 'daily')
            schedule_day = body.get('day_of_week') if frequency == 'weekly' else body.get('day_of_month')
            prefix = generate_scheduled_prefix(research_topic, frequency, schedule_day)
            return handle_scheduled(body, prefix)
        else:
            return handle_on_demand(body)
    
    elif path == '/invoke-agent':
        lambda_client = boto3.client('lambda', config=timeout_config)
        lambda_client.invoke(
            FunctionName=os.environ['CREATE_PROJECT_LAMBDA_ARN'],
            InvocationType='Event',
            Payload=json.dumps(json.loads(event.get('body', '{}')))
        )
        return {
            'statusCode': 202,
            'headers': CORS_HEADERS,
            'body': json.dumps({'message': 'Started Regeneration'})
        }
    
    return {
        'statusCode': 404,
        'headers': CORS_HEADERS,
        'body': json.dumps({'error': 'Path not found'})
    }
