import boto3
from strands import tool
import json
import os
from botocore.config import Config

timeout_config = Config(read_timeout=300)
retry_config = Config(
    read_timeout=300,
    retries={'total_max_attempts': 4, 'mode': 'standard'}
)


sts = boto3.client('sts', config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()['Account']

bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=os.environ.get('AWS_REGION'), config=retry_config)
s3_client = boto3.client('s3', region_name=os.environ.get('AWS_REGION'), config=timeout_config)


@tool(name="query_knowledge_customer_data", description="Retrieves details from the Knowledge base regarding customer data")
def query_knowledge_customer_data(query, customer):
    """
    Queries the knowledge base for customer data based on the provided query and customer.

    Args:
        query (str): The query to search for in the knowledge base.
        customer (str): The customer identifier to filter the results.

    Returns:
        list: A list of results retrieved from the knowledge base.
    """
    try:
        print("This is the query from the query_knowledge_customer_data tool: ",query)
        print("This is the customer from the query_knowledge_customer_data tool: ",customer)
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=os.environ.get('CUSTOMER_KNOWLEDGE_BASE_ID'),
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 5,
                    'filter': {
                        'listContains': {
                            'key': 'customer',
                            'value': customer
                        }
                    }
                }
            }
        )
        print("This is the response from the query_knowledge_customer_data tool: ",response)
        results = []
        for item in response.get('retrievalResults', []):
            results.append(item['content']['text'])
        print("This is the tool response from the query_knowledge_customer_data tool: ",results)
        return results
        
    except Exception as e:
        print("query_knwoledge_customer_data tool error: ",str(e))
        return {
            'error': str(e)
        }
    

@tool(name="query_knowledge_syndicate_data", description="Retrieves details from the Knowledge base regarding syndicate data")
def query_knowledge_syndicate_data(query, customer):
    """
    Queries the knowledge base for syndicate data based on the provided query and customer.

    Args:
        query (str): The query to search for in the knowledge base.
        customer (str): The customer identifier to filter the results.

    Returns:
        list: A list of results retrieved from the knowledge base.
    """
    try:
        print("This is the query from the query_knowledge_syndicate_data tool: ",query)
        print("This is the customer from the query_knowledge_syndicate_data tool: ",customer)
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=os.environ.get('SYNDICATE_KNOWLEDGE_BASE_ID'),
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 5,
                    'filter': {
                        'listContains': {
                            'key': 'customer',
                            'value': customer
                        }
                    }
                }
            }
        )
        print("This is the tool response from the query_knowledge_syndicate_data tool: ",response)
        results = []
        for item in response.get('retrievalResults', []):
            results.append(item['content']['text'])
        print("This is the tool response from the query_knowledge_syndicate_data tool: ",results)
        return results
        
    except Exception as e:
        print("query_knwoledge_syndicate_data tool error: ",str(e))
        return {
            'error': str(e)
        }

@tool(name="query_knowledge_historical_data", description="Retrieves details from the Knowledge base regarding historical data")
def query_knowledge_historical_data(query, customer):
    """
    Queries the knowledge base for historical data based on the provided query and customer.

    Args:
        query (str): The query to search for in the knowledge base.
        customer (str): The customer identifier to filter the results.

    Returns:
        list: A list of results retrieved from the knowledge base.
    """
    try:
        print("This is the query from the query_knowledge_historical_data tool: ",query)
        print("This is the customer from the query_knowledge_historical_data tool: ",customer)
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=os.environ.get('HISTORICAL_KNOWLEDGE_BASE_ID'),
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 5,
                    'filter': {
                        'listContains': {
                            'key': 'customer',
                            'value': customer
                        }
                    }
                }
            }
        )
        print("This is the tool response from the query_knowledge_historical_data tool: ",response)
        results = []
        for item in response.get('retrievalResults', []):
            results.append(item['content']['text'])
        print("This is the tool response from the query_knowledge_historical_data tool: ",results)
        return results
        
    except Exception as e:
        print("query_knowledge_historical_data tool error: ",str(e))
        return {
            'error': str(e)
        }


@tool(name="read_s3_content", description="Reads a JSON file from S3 and extracts the 'summary' field from each object in the list")
def read_s3_content(s3_object_key):
    """
    Reads a JSON file from S3 using the provided object key and extracts news content from each item.

    Args:
        s3_object_key (str): The S3 object key of the JSON file to read.

    Returns:
        list: A list of news content strings extracted from the JSON objects.
    """
    try:
        bucket_name = os.environ.get('CONTENT_S3_BUCKET_NAME')
        if not bucket_name:
            return {'error': 'CONTENT_S3_BUCKET_NAME environment variable is not set'}

        response = s3_client.get_object(Bucket=bucket_name, Key=s3_object_key, ExpectedBucketOwner=ACCOUNT_ID)
        file_content = response['Body'].read().decode('utf-8')
        data = json.loads(file_content)

        results = []
        for item in data:
            if 'summary' in item:
                results.append(item['summary'])

        print("This is the tool response from the read_s3_content tool: ",results)

        return {"related_content": results}

    except Exception as e:
        print("read_s3_content tool error: ", str(e))
        return {
            'error': str(e)
        }
