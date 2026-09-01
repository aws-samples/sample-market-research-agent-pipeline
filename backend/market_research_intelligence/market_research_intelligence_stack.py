from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_stepfunctions as sfn,
    aws_iam as iam,
    aws_bedrock as bedrock,
    aws_s3vectors as s3vectors,
    aws_s3 as s3,
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_logs as logs,
    aws_events as events,
    aws_events_targets as targets,
    CfnOutput
)
import aws_cdk.aws_bedrock_agentcore_alpha as agentcore
from aws_cdk.aws_ecr_assets import Platform
from constructs import Construct
import json
from pathlib import Path


# Constants for IAM and Lambda to resolve SonarQube duplicated string literal issues
LAMBDA_BASIC_EXECUTION_ROLE = "service-role/AWSLambdaBasicExecutionRole"
LAMBDA_SERVICE_PRINCIPAL = "lambda.amazonaws.com"
S3_GET_OBJECT = "s3:GetObject"
S3_PUT_OBJECT = "s3:PutObject"
LAMBDA_HANDLER = "lambda_function.lambda_handler"
BEDROCK_INVOKE_MODEL = "bedrock:InvokeModel"
SECRETS_MANAGER_GET_SECRET = "secretsmanager:GetSecretValue" # nosec
BEDROCK_SERVICE_PRINCIPAL = "bedrock.amazonaws.com"
COND_AWS_SOURCE_ACCOUNT = "aws:SourceAccount"
COND_AWS_SOURCE_ARN = "aws:SourceArn"


AWS_MP_SUBSCRIBE = "aws-marketplace:Subscribe"
AWS_MP_VIEW_SUBS = "aws-marketplace:ViewSubscriptions"
AWS_MP_UNSUBSCRIBE = "aws-marketplace:Unsubscribe"
COND_AWS_CALLED_VIA_LAST = "aws:CalledViaLast"
S3_LIST_BUCKET = "s3:ListBucket"
COND_AWS_RESOURCE_ACCOUNT = "aws:ResourceAccount"
S3VECTORS_GET_INDEX = "s3vectors:GetIndex"
S3VECTORS_QUERY_VECTORS = "s3vectors:QueryVectors"
S3VECTORS_PUT_VECTORS = "s3vectors:PutVectors"
S3VECTORS_GET_VECTORS = "s3vectors:GetVectors"
S3VECTORS_DELETE_VECTORS = "s3vectors:DeleteVectors"
STATES_START_EXECUTION = "states:StartExecution"
EVENT_SOURCE_AWS_S3 = "aws.s3"
EVENT_DETAIL_OBJ_CREATED = "Object Created"
EVENT_PATH_DETAIL = "$.detail"

class MarketResearchIntelligenceStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        with open("config.json", encoding="utf-8") as f:
            config = json.load(f)

        # ===========
        # s3 buckets
        # ===========

        content_store_s3 = s3.Bucket(
            self,
            "ContentStoreBucket",
            bucket_name=config["CONTENT_STORE_BUCKET"],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
        )

        raw_content_output_bucket = s3.Bucket(
            self,
            "RawContentOutputBucket",
            bucket_name=config["RAW_CONTENT_OUTPUT_BUCKET"],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
        )

        domains_config_s3 = s3.Bucket(
            self,
            "DomainsConfigBucket",
            bucket_name=config["DOMAINS_CONFIG_S3_BUCKET"],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.HEAD,
                    ],
                    allowed_origins=[
                        "http://localhost:*",
                        config["FRONTEND_URL"],
                    ],
                    allowed_headers=["*"],
                    exposed_headers=[
                        "ETag",
                        "x-amz-meta-custom-header",
                    ],
                    max_age=3000,
                )
            ],
        )

        customer_data_s3_bucket = s3.Bucket(
            self,
            "CustomerDataBucket",
            bucket_name=config["CUSTOMER_DATA_BUCKET"],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            event_bridge_enabled=True,
            enforce_ssl=True,
        )

        historical_data_s3_bucket = s3.Bucket(
            self,
            "HistoricalDataBucket",
            bucket_name=config["HISTORICAL_DATA_BUCKET"],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            event_bridge_enabled=True,
            enforce_ssl=True,
        )

        syndicate_data_s3_bucket = s3.Bucket(
            self,
            "SyndicateDataBucket",
            bucket_name=config["SYNDICATE_DATA_BUCKET"],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            event_bridge_enabled=True,
            enforce_ssl=True,
        )

        customer_data_kb_data_source_s3_bucket = s3.Bucket(
            self,
            "CustomerDataKBDataSourceBucket",
            bucket_name=f"{config['CUSTOMER_DATA_BUCKET']}-kb",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
        )

        historical_data_kb_data_source_s3_bucket = s3.Bucket(
            self,
            "HistoricalDataKBDataSourceBucket",
            bucket_name=f"{config['HISTORICAL_DATA_BUCKET']}-kb",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
        )

        syndicate_data_kb_data_source_s3_bucket = s3.Bucket(
            self,
            "SyndicateDataKBDataSourceBucket",
            bucket_name=f"{config['SYNDICATE_DATA_BUCKET']}-kb",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
        )

        # ====================
        # NOTE: The API keys secret is created manually as a prerequisite before deploying
        # this stack. Fill in API_KEYS_SECRET_ARN in config.json with the full secret ARN.
        # Lambdas receive the ARN as API_KEYS_SECRET_NAME env var and call get_secret_value.
        # ====================
        api_keys_secret_arn = config['API_KEYS_SECRET_ARN']

        # =========================
        # IAM ROLE FOR ENRICHMENT LAMBDA
        enrichment_lambda_role = iam.Role(
            self,
            "EnrichmentLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for enrichment Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        enrichment_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )

        enrichment_s3_arn = f"arn:aws:s3:::{config['ENRICHMENT_S3_BUCKET_NAME']}"
        enrichment_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    S3_GET_OBJECT
                ],
                resources=[
                    enrichment_s3_arn,
                    f"{enrichment_s3_arn}/*"
                ]
            )
        )

        # ENRICHMENT LAMBDA FUNCTION
        enrichment_lambda = _lambda.Function(
            self,
            "EnrichmentLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler=LAMBDA_HANDLER,
            code=_lambda.Code.from_asset("market_research_intelligence/lambdas/enrichment_lambda"),
            role=enrichment_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=1024,
            environment={
                "CONTENT_STORE_BUCKET": config['CONTENT_STORE_BUCKET'],
            }
        )

        content_store_s3.grant_read_write(enrichment_lambda)
        domains_config_s3.grant_read(enrichment_lambda)

        # =========================
        # IAM ROLE FOR CATEGORIZATION LAMBDA
        categorization_layer_lambda_role = iam.Role(
            self,
            "CategorizationLayerLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for categorization Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        categorization_layer_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )
        content_store_s3_arn = f"arn:aws:s3:::{config['CONTENT_STORE_BUCKET']}/*"
        categorization_layer_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    BEDROCK_INVOKE_MODEL,
                    S3_GET_OBJECT,
                    S3_PUT_OBJECT
                ],
                resources=[
                    content_store_s3_arn,
                    config['MODEL_INFERENCE_PROFILE'],
                    f"arn:aws:bedrock:*::foundation-model/{config['FOUNDATION_MODEL_ID']}"
                ]
            )
        )

        # CATEGORIZATION LAMBDA FUNCTION
        categorization_layer_lambda = _lambda.Function(
            self,
            "CategorizationLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler=LAMBDA_HANDLER,
            code=_lambda.Code.from_asset("market_research_intelligence/lambdas/categorization_layer_lambda"),
            role=categorization_layer_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=1024,
            environment={
                "MODEL_INFERENCE_PROFILE": config["MODEL_INFERENCE_PROFILE"]
            }
        )

        # =========================
        # IAM ROLE FOR WEB SEARCH LAMBDA
        web_search_lambda_role = iam.Role(
            self,
            "WebSearchLambdaIam",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for web search Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        web_search_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )
        domains_config_s3_arn = f"arn:aws:s3:::{config['DOMAINS_CONFIG_S3_BUCKET']}/*"
        web_search_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    S3_GET_OBJECT,
                    S3_PUT_OBJECT
                ],
                resources=[
                    content_store_s3_arn,
                    domains_config_s3_arn
                ]
            )
        )

        web_search_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[SECRETS_MANAGER_GET_SECRET],
                resources=[api_keys_secret_arn]
            )
        )

        # SYNC KB LAMBDA FUNCTION
        web_search_lambda = _lambda.DockerImageFunction(
            self,
            "WebSearchLambda",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="market_research_intelligence/lambdas/web_search_lambda"
            ),
            role=web_search_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=2048,
            environment={
                "MAX_TOKENS_PER_PAGE": config["MAX_TOKENS_PER_PAGE"],
                "MAX_RESULTS": config["MAX_RESULTS"],
                "DOMAINS_CONFIG_S3_URI": config['DOMAINS_CONFIG_S3_URI'],
                "API_KEYS_SECRET_NAME": api_keys_secret_arn
            }
        )

        # =========================
        # CUSTOMER DATA KNOWLEDGE BASE
        # =========================

        customer_data_kb_vector_bucket = s3vectors.CfnVectorBucket(self, "CustomerDataKBVectorBucket",
            vector_bucket_name= f"{config['CUSTOMER_DATA_BUCKET']}-vs"
        )

        customer_data_kb_vector_index = s3vectors.CfnIndex(self, "CustomerDataKBVectorIndex",
            dimension= 1024,
            distance_metric= "euclidean",
            data_type = "float32",
            vector_bucket_arn= customer_data_kb_vector_bucket.attr_vector_bucket_arn,
            metadata_configuration={
                "nonFilterableMetadataKeys":['AMAZON_BEDROCK_TEXT','AMAZON_BEDROCK_METADATA']
            },
        )

        customer_data_kb_role = iam.Role(
            self,
            "CustomerDataKnowledgeBaseServiceRole",
            assumed_by=iam.ServicePrincipal(
                BEDROCK_SERVICE_PRINCIPAL,
                conditions={
                    "StringEquals": {
                        COND_AWS_SOURCE_ACCOUNT: self.account
                    },
                    "ArnLike": {
                        COND_AWS_SOURCE_ARN: f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"
                    }
                }
            ),
            description="Service role for Bedrock Knowledge Base"
        )

        embedding_model_arn= f"arn:aws:bedrock:{self.region}::foundation-model/{config['EMBEDDING_MODEL_FOR_KB']}"
        customer_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvokeModelStatement",
                effect=iam.Effect.ALLOW,
                actions=[BEDROCK_INVOKE_MODEL],
                resources=[embedding_model_arn]
            )
        )

        customer_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="MarketplaceOperationsFromBedrockFor3pModels",
                effect=iam.Effect.ALLOW,
                actions=[
                    AWS_MP_SUBSCRIBE,
                    AWS_MP_VIEW_SUBS,
                    AWS_MP_UNSUBSCRIBE
                ],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        COND_AWS_CALLED_VIA_LAST: BEDROCK_SERVICE_PRINCIPAL
                    }
                }
            )
        )
        
        customer_data_kb_source_s3_arn = f"arn:aws:s3:::{config['CUSTOMER_DATA_BUCKET']}-kb"
        customer_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3ListBucketStatement",
                effect=iam.Effect.ALLOW,
                actions=[S3_LIST_BUCKET,S3_GET_OBJECT],
                resources=[customer_data_kb_source_s3_arn,f"{customer_data_kb_source_s3_arn}/*"],
                conditions={
                    "StringEquals": {
                        COND_AWS_RESOURCE_ACCOUNT: self.account
                    }
                }
            )
        )

        customer_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3VectorsPermissions",
                effect=iam.Effect.ALLOW,
                actions=[
                    S3VECTORS_GET_INDEX,
                    S3VECTORS_QUERY_VECTORS,
                    S3VECTORS_PUT_VECTORS,
                    S3VECTORS_GET_VECTORS,
                    S3VECTORS_DELETE_VECTORS
                ],
                resources=[
                    customer_data_kb_vector_bucket.attr_vector_bucket_arn,
                    customer_data_kb_vector_index.attr_index_arn,
                    f"{customer_data_kb_vector_bucket.attr_vector_bucket_arn}/*"
                ]
            )
        )

        customer_data_knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "CustomerDataKnowledgeBase",
            name=config['CUSTOMER_DATA_KNOWLEDGE_BASE_NAME'],
            role_arn=customer_data_kb_role.role_arn,
            knowledge_base_configuration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": embedding_model_arn
                }
            },
            storage_configuration = {
                "type": "S3_VECTORS",
                "s3VectorsConfiguration": { 
                    "indexArn": customer_data_kb_vector_index.attr_index_arn,  
                    "indexName": customer_data_kb_vector_index.index_name,     
                    "vectorBucketArn": customer_data_kb_vector_bucket.attr_vector_bucket_arn  
                }
            }
        )

        customer_data_knowledge_base.node.add_dependency(customer_data_kb_role)

        customer_data_kb_data_source = bedrock.CfnDataSource(
            self,
            "CustomerDataKBDataSource",
            name = f"{config['CUSTOMER_DATA_KNOWLEDGE_BASE_NAME']}-data-source-1",
            knowledge_base_id=customer_data_knowledge_base.ref,
            data_source_configuration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": f"arn:aws:s3:::{config['CUSTOMER_DATA_BUCKET']}-kb"
                }
            },
            vector_ingestion_configuration={
                "chunkingConfiguration":{
                    "chunkingStrategy": "FIXED_SIZE",
                    "fixedSizeChunkingConfiguration": {
                        "maxTokens": 300,
                        "overlapPercentage": 20
                    }
                }
            }
        )

        # Ensure data source only runs after the KB is created
        customer_data_kb_data_source.add_depends_on(customer_data_knowledge_base)

        CfnOutput(self, "CustomerDataKnowledgeBaseID", value=customer_data_knowledge_base.ref)
        CfnOutput(self, "CustomerDataKBDataSourceID", value=customer_data_kb_data_source.attr_data_source_id)

        # =========================
        # SYNDICATE DATA KNOWLEDGE BASE
        # =========================

        syndicate_data_kb_vector_bucket = s3vectors.CfnVectorBucket(self, "SyndicateDataKBVectorBucket",
            vector_bucket_name= f"{config['SYNDICATE_DATA_BUCKET']}-vs"
        )

        syndicate_data_kb_vector_index = s3vectors.CfnIndex(self, "SyndicateDataKBVectorIndex",
            dimension= 1024,
            distance_metric= "euclidean",
            data_type = "float32",
            vector_bucket_arn= syndicate_data_kb_vector_bucket.attr_vector_bucket_arn,
            metadata_configuration={
                "nonFilterableMetadataKeys":['AMAZON_BEDROCK_TEXT','AMAZON_BEDROCK_METADATA']
            },
        )

        syndicate_data_kb_role = iam.Role(
            self,
            "SyndicateDataKnowledgeBaseServiceRole",
            assumed_by=iam.ServicePrincipal(
                BEDROCK_SERVICE_PRINCIPAL,
                conditions={
                    "StringEquals": {
                        COND_AWS_SOURCE_ACCOUNT: self.account
                    },
                    "ArnLike": {
                        COND_AWS_SOURCE_ARN: f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"
                    }
                }
            ),
            description="Service role for Syndicate Data Bedrock Knowledge Base"
        )

        embedding_model_arn= f"arn:aws:bedrock:{self.region}::foundation-model/{config['EMBEDDING_MODEL_FOR_KB']}"
        syndicate_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvokeModelStatement",
                effect=iam.Effect.ALLOW,
                actions=[BEDROCK_INVOKE_MODEL],
                resources=[embedding_model_arn]
            )
        )

        syndicate_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="MarketplaceOperationsFromBedrockFor3pModels",
                effect=iam.Effect.ALLOW,
                actions=[
                    AWS_MP_SUBSCRIBE,
                    AWS_MP_VIEW_SUBS,
                    AWS_MP_UNSUBSCRIBE
                ],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        COND_AWS_CALLED_VIA_LAST: BEDROCK_SERVICE_PRINCIPAL
                    }
                }
            )
        )
        
        syndicate_data_kb_source_s3_arn = f"arn:aws:s3:::{config['SYNDICATE_DATA_BUCKET']}-kb"
        syndicate_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3ListBucketStatement",
                effect=iam.Effect.ALLOW,
                actions=[S3_LIST_BUCKET,S3_GET_OBJECT],
                resources=[syndicate_data_kb_source_s3_arn,f"{syndicate_data_kb_source_s3_arn}/*"],
                conditions={
                    "StringEquals": {
                        COND_AWS_RESOURCE_ACCOUNT: self.account
                    }
                }
            )
        )

        syndicate_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3VectorsPermissions",
                effect=iam.Effect.ALLOW,
                actions=[
                    S3VECTORS_GET_INDEX,
                    S3VECTORS_QUERY_VECTORS,
                    S3VECTORS_PUT_VECTORS,
                    S3VECTORS_GET_VECTORS,
                    S3VECTORS_DELETE_VECTORS
                ],
                resources=[
                    syndicate_data_kb_vector_bucket.attr_vector_bucket_arn,
                    syndicate_data_kb_vector_index.attr_index_arn,
                    f"{syndicate_data_kb_vector_bucket.attr_vector_bucket_arn}/*"
                ]
            )
        )

        syndicate_data_knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "SyndicateDataKnowledgeBase",
            name=config['SYNDICATE_DATA_KNOWLEDGE_BASE_NAME'],
            role_arn=syndicate_data_kb_role.role_arn,
            knowledge_base_configuration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": embedding_model_arn
                }
            },
            storage_configuration = {
                "type": "S3_VECTORS",
                "s3VectorsConfiguration": { 
                    "indexArn": syndicate_data_kb_vector_index.attr_index_arn,  
                    "indexName": syndicate_data_kb_vector_index.index_name,     
                    "vectorBucketArn": syndicate_data_kb_vector_bucket.attr_vector_bucket_arn  
                }
            }
        )

        syndicate_data_knowledge_base.node.add_dependency(syndicate_data_kb_role)

        syndicate_data_kb_data_source = bedrock.CfnDataSource(
            self,
            "SyndicateDataKBDataSource",
            name = f"{config['SYNDICATE_DATA_KNOWLEDGE_BASE_NAME']}-data-source-1",
            knowledge_base_id = syndicate_data_knowledge_base.ref,
            data_source_configuration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": f"arn:aws:s3:::{config['SYNDICATE_DATA_BUCKET']}-kb"
                }
            },
            vector_ingestion_configuration={
                "chunkingConfiguration":{
                    "chunkingStrategy": "FIXED_SIZE",
                    "fixedSizeChunkingConfiguration": {
                        "maxTokens": 300,
                        "overlapPercentage": 20
                    }
                }
            }
        )

        # Ensure data source only runs after the KB is created
        syndicate_data_kb_data_source.add_depends_on(syndicate_data_knowledge_base)

        CfnOutput(self, "SyndicateDataKnowledgeBaseID", value=syndicate_data_knowledge_base.ref)
        CfnOutput(self, "SyndicateDataKBDataSourceID", value=syndicate_data_kb_data_source.attr_data_source_id)

        # =========================
        # HISTORICAL DATA KNOWLEDGE BASE
        # =========================

        historical_data_kb_vector_bucket = s3vectors.CfnVectorBucket(self, "HistoricalDataKBVectorBucket",
            vector_bucket_name= f"{config['HISTORICAL_DATA_BUCKET']}-vs"
        )

        historical_data_kb_vector_index = s3vectors.CfnIndex(self, "HistoricalDataKBVectorIndex",
            dimension= 1024,
            distance_metric= "euclidean",
            data_type = "float32",
            vector_bucket_arn= historical_data_kb_vector_bucket.attr_vector_bucket_arn,
            metadata_configuration={
                "nonFilterableMetadataKeys":['AMAZON_BEDROCK_TEXT','AMAZON_BEDROCK_METADATA']
            },
        )

        historical_data_kb_role = iam.Role(
            self,
            "HistoricalDataKnowledgeBaseServiceRole",
            assumed_by=iam.ServicePrincipal(
                BEDROCK_SERVICE_PRINCIPAL,
                conditions={
                    "StringEquals": {
                        COND_AWS_SOURCE_ACCOUNT: self.account
                    },
                    "ArnLike": {
                        COND_AWS_SOURCE_ARN: f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"
                    }
                }
            ),
            description="Service role for Historical Data Bedrock Knowledge Base"
        )

        historical_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvokeModelStatement",
                effect=iam.Effect.ALLOW,
                actions=[BEDROCK_INVOKE_MODEL],
                resources=[embedding_model_arn]
            )
        )

        historical_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="MarketplaceOperationsFromBedrockFor3pModels",
                effect=iam.Effect.ALLOW,
                actions=[
                    AWS_MP_SUBSCRIBE,
                    AWS_MP_VIEW_SUBS,
                    AWS_MP_UNSUBSCRIBE
                ],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        COND_AWS_CALLED_VIA_LAST: BEDROCK_SERVICE_PRINCIPAL
                    }
                }
            )
        )
        
        historical_data_kb_source_s3_arn = f"arn:aws:s3:::{config['HISTORICAL_DATA_BUCKET']}-kb"
        historical_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3ListBucketStatement",
                effect=iam.Effect.ALLOW,
                actions=[S3_LIST_BUCKET,S3_GET_OBJECT],
                resources=[historical_data_kb_source_s3_arn,f"{historical_data_kb_source_s3_arn}/*"],
                conditions={
                    "StringEquals": {
                        COND_AWS_RESOURCE_ACCOUNT: self.account
                    }
                }
            )
        )

        historical_data_kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3VectorsPermissions",
                effect=iam.Effect.ALLOW,
                actions=[
                    S3VECTORS_GET_INDEX,
                    S3VECTORS_QUERY_VECTORS,
                    S3VECTORS_PUT_VECTORS,
                    S3VECTORS_GET_VECTORS,
                    S3VECTORS_DELETE_VECTORS
                ],
                resources=[
                    historical_data_kb_vector_bucket.attr_vector_bucket_arn,
                    historical_data_kb_vector_index.attr_index_arn,
                    f"{historical_data_kb_vector_bucket.attr_vector_bucket_arn}/*"
                ]
            )
        )

        historical_data_knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "HistoricalDataKnowledgeBase",
            name=config['HISTORICAL_DATA_KNOWLEDGE_BASE_NAME'],
            role_arn=historical_data_kb_role.role_arn,
            knowledge_base_configuration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": embedding_model_arn
                }
            },
            storage_configuration = {
                "type": "S3_VECTORS",
                "s3VectorsConfiguration": { 
                    "indexArn": historical_data_kb_vector_index.attr_index_arn,  
                    "indexName": historical_data_kb_vector_index.index_name,     
                    "vectorBucketArn": historical_data_kb_vector_bucket.attr_vector_bucket_arn  
                }
            }
        )

        historical_data_knowledge_base.node.add_dependency(historical_data_kb_role)

        historical_data_kb_data_source = bedrock.CfnDataSource(
            self,
            "HistoricalDataKBDataSource",
            name = f"{config['HISTORICAL_DATA_KNOWLEDGE_BASE_NAME']}-data-source-1",
            knowledge_base_id = historical_data_knowledge_base.ref,
            data_source_configuration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": f"arn:aws:s3:::{config['HISTORICAL_DATA_BUCKET']}-kb"
                }
            },
            vector_ingestion_configuration={
                "chunkingConfiguration":{
                    "chunkingStrategy": "FIXED_SIZE",
                    "fixedSizeChunkingConfiguration": {
                        "maxTokens": 300,
                        "overlapPercentage": 20
                    }
                }
            }
        )

        # Ensure data source only runs after the KB is created
        historical_data_kb_data_source.add_depends_on(historical_data_knowledge_base)

        CfnOutput(self, "HistoricalDataKnowledgeBaseID", value=historical_data_knowledge_base.ref)
        CfnOutput(self, "HistoricalDataKBDataSourceID", value=historical_data_kb_data_source.attr_data_source_id)


        # ====================
        # IAM ROLE FOR DE DUP MERGE LAMBDA
        de_dup_lambda_role = iam.Role(
            self,
            "DeDupLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for de duplication and merge Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        de_dup_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )
        de_dup_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    BEDROCK_INVOKE_MODEL
                ],
                resources=[
                    config['MODEL_INFERENCE_PROFILE'],
                    f"arn:aws:bedrock:*::foundation-model/{config['FOUNDATION_MODEL_ID']}",
                    f"arn:aws:bedrock:{self.region}::foundation-model/{config['EMBEDDING_MODEL_FOR_KB']}"
                ]
            )
        )

        # DE DUP LAMBDA FUNCTION 
        de_dup_lambda = _lambda.DockerImageFunction(
            self,
            "DeDupLambda",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="market_research_intelligence/lambdas/de_duplication_merge_lambda"
            ),
            role=de_dup_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=2048,
            environment={
                "EMBEDDING_MODEL_FOR_KB": config['EMBEDDING_MODEL_FOR_KB'],
                "CONTENT_STORE_BUCKET": config['CONTENT_STORE_BUCKET'],
                "MODEL_INFERENCE_PROFILE": config['MODEL_INFERENCE_PROFILE'],
                "COSINE_SIMILARITY_THRESHOLD": config['COSINE_SIMILARITY_THRESHOLD'],
                "RAW_CONTENT_OUTPUT_BUCKET": config['RAW_CONTENT_OUTPUT_BUCKET']
            }
        )

        raw_content_output_bucket.grant_read_write(de_dup_lambda)
        content_store_s3.grant_read_write(de_dup_lambda)

        # ====================
        # IAM ROLE FOR NO RECORDS LAMBDA
        no_records_lambda_role = iam.Role(
            self,
            "NoRecordsLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for no records Lambda function"
        )

        no_records_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )

        no_records_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[S3_PUT_OBJECT],
                resources=[f"arn:aws:s3:::{config['AGENT_RESULTS_BUCKET']}/*"]
            )
        )

        # NO RECORDS LAMBDA FUNCTION
        no_records_lambda = _lambda.Function(
            self,
            "NoRecordsLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler=LAMBDA_HANDLER,
            code=_lambda.Code.from_asset("market_research_intelligence/lambdas/no_records_lambda"),
            role=no_records_lambda_role,
            timeout=Duration.seconds(300),
            memory_size=1028,
            environment={
                "AGENT_RESULTS_BUCKET": config['AGENT_RESULTS_BUCKET']
            }
        )

        # ====================
        # IAM ROLE FOR PRESS RELEASE LAMBDA
        press_release_lambda_role = iam.Role(
            self,
            "PressReleaseLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for press release Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        press_release_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )

        # CURATED NEWS ITEM LAMBDA FUNCTION
        press_release_lambda = _lambda.DockerImageFunction(
            self,
            "PressReleaseLambda",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="market_research_intelligence/lambdas/press_release_lambda"
            ),
            role=press_release_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=2048,
            environment={
                "INGESTION_PIPELINE_NAME": "web-pressreleases",
                "LINKS_BATCH_SIZE": config["LINKS_BATCH_SIZE"],
                "PAGINATION_SERP": config["PAGINATION_SERP"],
                "PRESS_RELEASE_CONFIG_S3_URI": config['PRESS_RELEASE_CONFIG_S3_URI'],
                "API_KEYS_SECRET_NAME": api_keys_secret_arn
            }
        )

        content_store_s3.grant_read_write(press_release_lambda)

        press_release_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[SECRETS_MANAGER_GET_SECRET],
                resources=[api_keys_secret_arn]
            )
        )
        domains_config_s3.grant_read(press_release_lambda)

        # ====================
        # IAM ROLE FOR PRESS RELEASE LAMBDA
        domain_scraper_lambda_role = iam.Role(
            self,
            "DomainScraperLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for domain scraper Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        domain_scraper_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )

        # CURATED NEWS ITEM LAMBDA FUNCTION
        domain_scraper_lambda = _lambda.DockerImageFunction(
            self,
            "DomainScraperLambda",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="market_research_intelligence/lambdas/domain_scraper_lambda"
            ),
            role=domain_scraper_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=2048,
            environment={
                "LINKS_BATCH_SIZE": config["LINKS_BATCH_SIZE"],
                "PAGINATION_SERP": config["PAGINATION_SERP"],
                "PRESS_RELEASE_CONFIG_S3_URI": config['PRESS_RELEASE_CONFIG_S3_URI'],
                "API_KEYS_SECRET_NAME": api_keys_secret_arn
            }
        )

        domain_scraper_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[SECRETS_MANAGER_GET_SECRET],
                resources=[api_keys_secret_arn]
            )
        )

        content_store_s3.grant_read_write(domain_scraper_lambda)

        # ====================
        # IAM ROLE FOR API CONNECTOR LAMBDA
        api_connector_lambda_role = iam.Role(
            self,
            "ApiConnectorLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for API connector Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        api_connector_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )

        # Secrets Manager read access (for Crunchbase API key)
        api_connector_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[SECRETS_MANAGER_GET_SECRET],
                resources=[api_keys_secret_arn]
            )
        )

        # API CONNECTOR LAMBDA FUNCTION
        api_connector_lambda = _lambda.DockerImageFunction(
            self,
            "ApiConnectorLambda",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="market_research_intelligence/lambdas/api_connector_lambda"
            ),
            role=api_connector_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=2048,
            environment={
                "INGESTION_PIPELINE_NAME": "deal_intelligence",
                "DATA_SOURCE_TYPE": config["DATA_SOURCE_TYPE"],
                "DATA_SOURCE_API_URL": config["DATA_SOURCE_API_URL"],
                "API_KEYS_SECRET_NAME": api_keys_secret_arn,
                "PAGESIZE": config["DEAL_INTELLIGENCE_PAGE_SIZE"],
                "MAX_PAGES": config["DEAL_INTELLIGENCE_MAX_PAGES"]
            }
        )

        content_store_s3.grant_read_write(api_connector_lambda)


        #######################
        #  AGENT CORE HOSTING
        #######################

        # --- IAM Role for Agent Core Runtime ---
        agent_core_runtime_role = iam.Role(
            self,
            "AgentCoreRuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Service role for Bedrock Agent Core Runtime"
        )

        # CloudWatch Logs permissions
        agent_core_runtime_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                resources=["arn:aws:logs:*:*:*"]
            )
        )

        # ECR pull permissions
        agent_core_runtime_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetAuthorizationToken"
                ],
                resources=["*"]
            )
        )

        # Bedrock model invocation permissions
        agent_core_runtime_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    BEDROCK_INVOKE_MODEL,
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    config['MODEL_INFERENCE_PROFILE'],
                    f"arn:aws:bedrock:*::foundation-model/{config['FOUNDATION_MODEL_ID']}",
                ]
            )
        )

        # S3 read/write permissions
        # TODO: Replace these bucket names with actual bucket names
        agent_core_runtime_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    S3_GET_OBJECT,
                    S3_PUT_OBJECT,
                    S3_LIST_BUCKET,
                    "s3:DeleteObject"
                ],
                resources=[
                    f"arn:aws:s3:::{config['RAW_CONTENT_OUTPUT_BUCKET']}",
                    f"arn:aws:s3:::{config['RAW_CONTENT_OUTPUT_BUCKET']}/*",
                ]
            )
        )

        # Bedrock KB Retrieve permissions (used by kb_query_tool.py)
        agent_core_runtime_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:Retrieve"],
                resources=[f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"]
            )
        )

        # --- Agent Runtime Artifact (Docker image from agent-code/) ---
        agent_runtime_artifact = agentcore.AgentRuntimeArtifact.from_asset(
            directory="agent-code",
            platform=Platform.LINUX_ARM64,
        )

        # --- Bedrock Agent Core Runtime ---
        agent_core_runtime = agentcore.Runtime(
            self,
            "AgentCoreRuntime",
            runtime_name=config["AGENT_CORE_RUNTIME_NAME"],
            agent_runtime_artifact=agent_runtime_artifact,
            execution_role=agent_core_runtime_role,
            environment_variables={
                "CONTENT_S3_BUCKET_NAME": config["RAW_CONTENT_OUTPUT_BUCKET"],
                "AWS_REGION": config["AWS_REGION"],
                "CUSTOMER_KNOWLEDGE_BASE_ID": customer_data_knowledge_base.ref,
                "SYNDICATE_KNOWLEDGE_BASE_ID": syndicate_data_knowledge_base.ref,
                "HISTORICAL_KNOWLEDGE_BASE_ID": historical_data_knowledge_base.ref,
                "MODEL_INFERENCE_PROFILE": config["MODEL_INFERENCE_PROFILE"]
            }
        )

        # # --- Add a Runtime Endpoint ---
        # agent_core_endpoint = agent_core_runtime.add_endpoint(
        #     endpoint_name=f"{config['AGENT_CORE_RUNTIME_NAME']}_endpoint"
        # )

        CfnOutput(self, "AgentCoreRuntimeArn",
                  value=agent_core_runtime.agent_runtime_arn,
                  description="Bedrock Agent Core Runtime ARN")

        CfnOutput(self, "AgentCoreRuntimeId",
                  value=agent_core_runtime.agent_runtime_id,
                  description="Bedrock Agent Core Runtime ID")

        # ====================
        # IAM ROLE FOR INVOKE AGENT LAMBDA
        invoke_agent_lambda_role = iam.Role(
            self,
            "InvokeAgentLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for invoke agent Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        invoke_agent_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )

        # INVOKE AGENT LAMBDA FUNCTION
        invoke_agent_lambda = _lambda.Function(
            self,
            "InvokeAgentLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler=LAMBDA_HANDLER,
            code=_lambda.Code.from_asset("market_research_intelligence/lambdas/invoke_agent_lambda"),
            role=invoke_agent_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=2048,
            environment={
                "RESULTS_BUCKET": config['AGENT_RESULTS_BUCKET'],
                # "AWS_REGION": self.region,
                "AGENT_RUNTIME_ARN": agent_core_runtime.agent_runtime_arn
            }
        )

        raw_content_output_bucket.grant_read(invoke_agent_lambda)
        invoke_agent_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[S3_GET_OBJECT, S3_PUT_OBJECT],
                resources=[f"arn:aws:s3:::{config['AGENT_RESULTS_BUCKET']}/*"]
            )
        )


        invoke_agent_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=["*"]
            )
        )

        # ====================
        # INGESTION PIPELINE STEP FUNCTION
        # ====================

        asl_path = Path("market_research_intelligence/step_functions/definition.asl.json")
        asl_definition = asl_path.read_text()

        replacements = {
            "${EnrichmentLambdaArn}": enrichment_lambda.function_arn,
            "${WebSearchLambdaArn}": web_search_lambda.function_arn,
            "${PressReleaseLambdaArn}" : press_release_lambda.function_arn,
            "${DomainScraperLambdaArn}": domain_scraper_lambda.function_arn,
            "${CategorizationLayerLambdaArn}": categorization_layer_lambda.function_arn,
            "${DeDuplicationLambdaArn}" : de_dup_lambda.function_arn,
            "${InvokeAgentLambdaArn}": invoke_agent_lambda.function_arn,
            "${ApiConnectorLambdaArn}": api_connector_lambda.function_arn,
            "${NoRecordsLambdaArn}": no_records_lambda.function_arn,
        }

        for placeholder, value in replacements.items():
            asl_definition = asl_definition.replace(placeholder, value)

        ingestion_sfn_role = iam.Role(
            self,
            "IngestionStepFunctionRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com")
        )

        ingestion_state_machine = sfn.CfnStateMachine(
            self,
            "IngestionStateMachine",
            role_arn=ingestion_sfn_role.role_arn,
            definition_string=asl_definition,
            state_machine_type="STANDARD"
        )

        ingestion_sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3ListBucketStatement",
                effect=iam.Effect.ALLOW,
                actions=[S3_LIST_BUCKET],
                resources=[content_store_s3.bucket_arn],
            )
        )      

        ingestion_sfn_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[STATES_START_EXECUTION],
                resources=[ingestion_state_machine.attr_arn],
            )
        )

        ingestion_sfn_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "states:DescribeExecution",
                    "states:StopExecution",
                ],
                resources=[
                    f"arn:aws:states:{self.region}:{self.account}:execution:{ingestion_state_machine.attr_name}:*",
                    f"arn:aws:states:{self.region}:{self.account}:execution:{ingestion_state_machine.attr_name}/*",
                ],
            )
        )

        ingestion_sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="RedriveExecutionScopedPolicyForMapRun",
                effect=iam.Effect.ALLOW,
                actions=["states:RedriveExecution"],
                resources=[
                    f"arn:aws:states:{self.region}:{self.account}:execution:{ingestion_state_machine.attr_name}/*"
                ],
            )
        )

        enrichment_lambda.grant_invoke(ingestion_sfn_role)
        categorization_layer_lambda.grant_invoke(ingestion_sfn_role)
        web_search_lambda.grant_invoke(ingestion_sfn_role)
        press_release_lambda.grant_invoke(ingestion_sfn_role)
        domain_scraper_lambda.grant_invoke(ingestion_sfn_role)
        de_dup_lambda.grant_invoke(ingestion_sfn_role)
        invoke_agent_lambda.grant_invoke(ingestion_sfn_role)
        api_connector_lambda.grant_invoke(ingestion_sfn_role)
        no_records_lambda.grant_invoke(ingestion_sfn_role)


        # ====================
        # IAM ROLE FOR API HANDLER LAMBDA
        api_handler_lambda_role = iam.Role(
            self,
            "ApiHandlerLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for API handler Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        api_handler_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )

        # Permission to start the ingestion step function
        api_handler_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[STATES_START_EXECUTION],
                resources=[ingestion_state_machine.attr_arn]
            )
        )

        # Permission to invoke the invoke_agent lambda
        invoke_agent_lambda.grant_invoke(api_handler_lambda_role)

        # EventBridge Scheduler role for scheduled pipeline triggers
        scheduler_sf_role = iam.Role(
            self,
            "SchedulerStepFunctionRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            description="Role for EventBridge Scheduler to start the ingestion step function"
        )
        scheduler_sf_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[STATES_START_EXECUTION],
                resources=[ingestion_state_machine.attr_arn]
            )
        )

        # S3 PutObject on agent results bucket (for creating scheduled folder markers)
        api_handler_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[S3_PUT_OBJECT],
                resources=[f"arn:aws:s3:::{config['AGENT_RESULTS_BUCKET']}/*"]
            )
        )

        # EventBridge Scheduler permissions (for creating schedules)
        api_handler_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["scheduler:CreateSchedule"],
                resources=[f"arn:aws:scheduler:{self.region}:{self.account}:schedule/default/*"]
            )
        )

        # PassRole permission so Lambda can assign the Scheduler role to targets
        api_handler_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[scheduler_sf_role.role_arn]
            )
        )

        # API HANDLER LAMBDA FUNCTION
        api_handler_lambda = _lambda.Function(
            self,
            "ApiHandlerLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler=LAMBDA_HANDLER,
            code=_lambda.Code.from_asset("market_research_intelligence/lambdas/api_handler_lambda"),
            role=api_handler_lambda_role,
            timeout=Duration.seconds(150),
            memory_size=1024,
            environment={
                "SF_ARN": ingestion_state_machine.attr_arn,
                "CREATE_PROJECT_LAMBDA_ARN": invoke_agent_lambda.function_arn,
                "AGENT_RESULTS_BUCKET": config['AGENT_RESULTS_BUCKET'],
                "SCHEDULER_ROLE_ARN": scheduler_sf_role.role_arn
            }
        )

        # ====================
        # API GATEWAY
        # ====================

        # Import existing Cognito User Pool from Frontend stack
        user_pool = cognito.UserPool.from_user_pool_arn(
            self, "ImportedUserPool", config["COGNITO_USER_POOL_ARN"]
        )

        # Cognito Authorizer for API Gateway
        cognito_authorizer = apigw.CognitoUserPoolsAuthorizer(
            self, "CognitoAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name="CognitoAuthorizer",
        )

        # IAM Role for API Gateway to write CloudWatch Logs (account-level setting)
        api_gw_cloudwatch_role = iam.Role(
            self, "ApiGatewayCloudWatchRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonAPIGatewayPushToCloudWatchLogs"
                )
            ],
        )

        # Register the role at the API Gateway account level
        api_gw_account = apigw.CfnAccount(
            self, "ApiGatewayAccount",
            cloud_watch_role_arn=api_gw_cloudwatch_role.role_arn,
        )

        # API Gateway access log group
        api_log_group = logs.LogGroup(
            self, "ApiGatewayAccessLogs",
            retention=logs.RetentionDays.ONE_MONTH,
        )

        api = apigw.RestApi(
            self,
            "InvokeAgentApi",
            rest_api_name="Market Research Intelligence API",
            description="API Gateway for the Market Research Intelligence prototype",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
            ),
            deploy_options=apigw.StageOptions(
                access_log_destination=apigw.LogGroupLogDestination(api_log_group),
                access_log_format=apigw.AccessLogFormat.clf(),
                logging_level=apigw.MethodLoggingLevel.INFO,
            ),
        )

        # Ensure the API Gateway account settings (CloudWatch role) are applied before the stage
        api.node.add_dependency(api_gw_account)

        # Request validator for the API
        request_validator = api.add_request_validator(
            "RequestBodyValidator",
            validate_request_body=True,
        )

        # Lambda integration — both routes use the api_handler_lambda
        api_handler_integration = apigw.LambdaIntegration(
            api_handler_lambda,
            request_templates={"application/json": '{ "statusCode": "200" }'}
        )

        # Add /create-project resource with POST method (Cognito-protected)
        create_project_resource = api.root.add_resource("create-project")
        create_project_resource.add_method(
            "POST", api_handler_integration,
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=cognito_authorizer,
        )

        # Add /invoke-agent resource with POST method (Cognito-protected)
        invoke_agent_resource = api.root.add_resource("invoke-agent")
        invoke_agent_resource.add_method(
            "POST", api_handler_integration,
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=cognito_authorizer,
        )


        # Output the API Gateway URL
        CfnOutput(
            self,
            "ApiGatewayUrl",
            value=api.url,
            description="API Gateway base URL"
        )

        # ====================
        # IAM ROLE FOR DOCLING PREPROCESSING LAMBDA
        docling_preprocessing_lambda_role = iam.Role(
            self,
            "DoclingPreprocessingLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for docling preprocessing Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        docling_preprocessing_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )

        # DOCLING PREPROCESSING LAMBDA FUNCTION
        docling_preprocessing_lambda = _lambda.DockerImageFunction(
            self,
            "DoclingPreprocessingLambda",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="market_research_intelligence/lambdas/docling-preprocessing"
            ),
            role=docling_preprocessing_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=2048
        )

        customer_data_s3_bucket.grant_read_write(docling_preprocessing_lambda)
        historical_data_s3_bucket.grant_read_write(docling_preprocessing_lambda)
        syndicate_data_s3_bucket.grant_read_write(docling_preprocessing_lambda)

        # ====================
        # IAM ROLE FOR DOCLING EXTRACTION LAMBDA
        # ====================
        docling_extraction_lambda_role = iam.Role(
            self,
            "DoclingExtractionLambdaRole",
            assumed_by=iam.ServicePrincipal(LAMBDA_SERVICE_PRINCIPAL),
            description="IAM role for docling extraction Lambda function"
        )

        # Basic logging permission (CloudWatch Logs)
        docling_extraction_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                LAMBDA_BASIC_EXECUTION_ROLE
            )
        )

        # Bedrock Agent permissions (start and check KB ingestion jobs)
        docling_extraction_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:StartIngestionJob",
                    "bedrock:GetIngestionJob"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"
                ]
            )
        )

        # DOCLING EXTRACTION LAMBDA FUNCTION
        docling_extraction_lambda = _lambda.DockerImageFunction(
            self,
            "DoclingExtractionLambda",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="market_research_intelligence/lambdas/docling-extraction"
            ),
            role=docling_extraction_lambda_role,
            timeout=Duration.seconds(900),
            memory_size=3008,
            environment={}
        )

        # S3 read permissions on source buckets (to generate presigned URLs)
        customer_data_s3_bucket.grant_read(docling_extraction_lambda)
        historical_data_s3_bucket.grant_read(docling_extraction_lambda)
        syndicate_data_s3_bucket.grant_read(docling_extraction_lambda)

        customer_data_kb_data_source_s3_bucket.grant_read_write(docling_extraction_lambda)
        historical_data_kb_data_source_s3_bucket.grant_read_write(docling_extraction_lambda)
        syndicate_data_kb_data_source_s3_bucket.grant_read_write(docling_extraction_lambda)

        # =================================
        # DOCLING PIPELINE STEP FUNCTION 
        # =================================

        docling_asl_path = Path("market_research_intelligence/step_functions/docling-definition.asl.json")
        docling_asl_definition = docling_asl_path.read_text()

        docling_replacements = {
            "${DoclingPreProcessingLambdaArn}": docling_preprocessing_lambda.function_arn,
            "${DoclingExtractionLambdaArn}": docling_extraction_lambda.function_arn,
        }

        for placeholder, value in docling_replacements.items():
            docling_asl_definition = docling_asl_definition.replace(placeholder, value)

        docling_sfn_role = iam.Role(
            self,
            "DoclingStepFunctionRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com")
        )

        docling_state_machine = sfn.StateMachine(
            self,
            "DoclingStateMachine",
            definition_body=sfn.DefinitionBody.from_string(docling_asl_definition),
            state_machine_type=sfn.StateMachineType.STANDARD,
            role=docling_sfn_role
        )

        docling_preprocessing_lambda.grant_invoke(docling_state_machine)
        docling_extraction_lambda.grant_invoke(docling_state_machine)

        # Separate policy to avoid circular dependency with DefaultPolicy
        # (DefaultPolicy is depended on by StateMachine, so it can't reference the StateMachine back)
        iam.Policy(
            self,
            "DoclingStepFunctionExecutionPolicy",
            roles=[docling_sfn_role],
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "states:DescribeExecution",
                        "states:StopExecution",
                    ],
                    resources=[
                        f"arn:aws:states:{self.region}:{self.account}:execution:{docling_state_machine.state_machine_name}:*",
                        f"arn:aws:states:{self.region}:{self.account}:execution:{docling_state_machine.state_machine_name}/*",
                    ],
                ),
                iam.PolicyStatement(
                    sid="RedriveExecutionScopedPolicyForMapRun",
                    effect=iam.Effect.ALLOW,
                    actions=["states:RedriveExecution"],
                    resources=[
                        f"arn:aws:states:{self.region}:{self.account}:execution:{docling_state_machine.state_machine_name}/*"
                    ],
                ),
            ]
        )

        # ===========================================================
        # S3 EVENT -> STEP FUNCTION (with enriched payload)
        # ===========================================================

        # --- Rule for Customer Data Bucket ---
        customer_data_event_rule = events.Rule(
            self,
            "CustomerDataS3EventRule",
            rule_name="customer-data-s3-object-created",
            description="Triggers docling pipeline when objects are created in Customer Data bucket",
            event_pattern=events.EventPattern(
                source=[EVENT_SOURCE_AWS_S3],
                detail_type=[EVENT_DETAIL_OBJ_CREATED],
                detail={
                    "bucket": {
                        "name": [config["CUSTOMER_DATA_BUCKET"]]
                    }
                }
            )
        )

        customer_data_event_rule.add_target(
            targets.SfnStateMachine(
                docling_state_machine,
                input=events.RuleTargetInput.from_object({
                    "detail": events.EventField.from_path(EVENT_PATH_DETAIL),
                    "knowledge_base_id": customer_data_knowledge_base.ref,
                    "data_source_id": customer_data_kb_data_source.attr_data_source_id,
                    "output_bucket": customer_data_kb_data_source_s3_bucket.bucket_name
                })
            )
        )

        # --- Rule for Historical Data Bucket ---
        historical_data_event_rule = events.Rule(
            self,
            "HistoricalDataS3EventRule",
            rule_name="historical-data-s3-object-created",
            description="Triggers docling pipeline when objects are created in Historical Data bucket",
            event_pattern=events.EventPattern(
                source=[EVENT_SOURCE_AWS_S3],
                detail_type=[EVENT_DETAIL_OBJ_CREATED],
                detail={
                    "bucket": {
                        "name": [config["HISTORICAL_DATA_BUCKET"]]
                    }
                }
            )
        )

        historical_data_event_rule.add_target(
            targets.SfnStateMachine(
                docling_state_machine,
                input=events.RuleTargetInput.from_object({
                    "detail": events.EventField.from_path(EVENT_PATH_DETAIL),
                    "knowledge_base_id": historical_data_knowledge_base.ref,
                    "data_source_id": historical_data_kb_data_source.attr_data_source_id,
                    "output_bucket": historical_data_kb_data_source_s3_bucket.bucket_name
                })
            )
        )

        # --- Rule for Syndicate Data Bucket ---
        syndicate_data_event_rule = events.Rule(
            self,
            "SyndicateDataS3EventRule",
            rule_name="syndicate-data-s3-object-created",
            description="Triggers docling pipeline when objects are created in Syndicate Data bucket",
            event_pattern=events.EventPattern(
                source=[EVENT_SOURCE_AWS_S3],
                detail_type=[EVENT_DETAIL_OBJ_CREATED],
                detail={
                    "bucket": {
                        "name": [config["SYNDICATE_DATA_BUCKET"]]
                    }
                }
            )
        )

        syndicate_data_event_rule.add_target(
            targets.SfnStateMachine(
                docling_state_machine,
                input=events.RuleTargetInput.from_object({
                    "detail": events.EventField.from_path(EVENT_PATH_DETAIL),
                    "knowledge_base_id": syndicate_data_knowledge_base.ref,
                    "data_source_id": syndicate_data_kb_data_source.attr_data_source_id,
                    "output_bucket": syndicate_data_kb_data_source_s3_bucket.bucket_name
                })
            )
        )
