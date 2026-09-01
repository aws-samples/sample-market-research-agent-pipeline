import json
import os

from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
)
from constructs import Construct

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)


class FrontendStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ===========
        # S3 Bucket for Static Website Hosting
        # ===========
        website_bucket = s3.Bucket(
            self,
            "WebsiteBucket",
            bucket_name=config["s3_website_hosting_bucket_name"],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ===========
        # CloudFront Origin Access Identity
        # ===========
        origin_access_identity = cloudfront.OriginAccessIdentity(
            self,
            "OAI",
            comment="OAI for Market Research Intelligence App"
        )

        # Grant read access to CloudFront
        website_bucket.grant_read(origin_access_identity)

        # ===========
        # CloudFront Distribution
        # ===========
        distribution = cloudfront.Distribution(
            self,
            "WebsiteDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    website_bucket,
                    origin_access_identity=origin_access_identity
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
            ),
            default_root_object="index.html",
            # Minimum TLS 1.2 (satisfies AwsSolutions-CFR4)
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            error_responses=[
                # Handle SPA routing - return index.html for 404s
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
        )


        # CORS allowed origins
        cors_allowed_origins = [
            "http://localhost:*",
            f"https://{distribution.distribution_domain_name}",
        ]

        # ===========
        # S3 Bucket for Agent Results (with CORS for browser access)
        # ===========
        agent_results_bucket = s3.Bucket(
            self,
            "AgentResults",
            bucket_name=f"{config['agent_results_bucket']}-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.HEAD,
                    ],
                    allowed_origins=cors_allowed_origins,
                    allowed_headers=["*"],
                    exposed_headers=[
                        "ETag",
                        "x-amz-meta-custom-header",
                    ],
                    max_age=3000,
                )
            ],
        )

        # ===========
        # S3 Bucket for Enrichment Results (with CORS for browser access)
        # ===========
        enrichment_bucket = s3.Bucket(
            self,
            "EnrichmentResults",
            bucket_name=f"{config['enrichment_bucket']}-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.HEAD,
                        s3.HttpMethods.PUT,
                    ],
                    allowed_origins=cors_allowed_origins,
                    allowed_headers=["*"],
                    exposed_headers=[
                        "ETag",
                        "x-amz-meta-custom-header",
                    ],
                    max_age=3000,
                )
            ],
        )

        # ===========
        # Cognito User Pool (Login / Signup)
        # ===========
        user_pool = cognito.UserPool(
            self,
            "MarketResearchUserPool",
            user_pool_name=config["user_pool_name"],
            self_sign_up_enabled=config["self_sign_up_enabled"],
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,  # Fixed: AwsSolutions-COG1 requires symbols
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
        )


        # ===========
        # Cognito User Pool App Client
        # ===========
        user_pool_client = user_pool.add_client(
            "MarketResearchAppClient",
            user_pool_client_name=config["app_client_name"],
            generate_secret=False,  # No secret for SPA / browser apps
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            )
        )

        # ===========
        # Cognito Identity Pool (linked to User Pool)
        # ===========
        identity_pool = cognito.CfnIdentityPool(
            self,
            "MarketResearchIdentityPool",
            identity_pool_name=config["identity_pool_name"],
            allow_unauthenticated_identities=False,  # Only authenticated users allowed
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=user_pool_client.user_pool_client_id,
                    provider_name=user_pool.user_pool_provider_name,
                )
            ],
        )

        # # ===========
        # # IAM Role for Unauthenticated Users (COMMENTED OUT — only authenticated access needed)
        # # ===========
        # unauthenticated_role = iam.Role(
        #     self,
        #     "CognitoUnauthenticatedRole",
        #     assumed_by=iam.FederatedPrincipal(
        #         "cognito-identity.amazonaws.com",
        #         conditions={
        #             "StringEquals": {
        #                 "cognito-identity.amazonaws.com:aud": identity_pool.ref
        #             },
        #             "ForAnyValue:StringLike": {
        #                 "cognito-identity.amazonaws.com:amr": "unauthenticated"
        #             },
        #         },
        #         assume_role_action="sts:AssumeRoleWithWebIdentity",
        #     ),
        #     description="IAM role for unauthenticated Cognito users to access S3",
        # )
        #
        # # Grant S3 read permissions on agent results bucket
        # unauthenticated_role.add_to_policy(
        #     iam.PolicyStatement(
        #         effect=iam.Effect.ALLOW,
        #         actions=[
        #             "s3:GetObject",
        #             "s3:ListBucket",
        #         ],
        #         resources=[
        #             agent_results_bucket.bucket_arn,
        #             f"{agent_results_bucket.bucket_arn}/*",
        #         ],
        #     )
        # )
        #
        # # Grant S3 read/write permissions on enrichment bucket
        # unauthenticated_role.add_to_policy(
        #     iam.PolicyStatement(
        #         effect=iam.Effect.ALLOW,
        #         actions=[
        #             "s3:GetObject",
        #             "s3:PutObject",
        #             "s3:ListBucket",
        #         ],
        #         resources=[
        #             enrichment_bucket.bucket_arn,
        #             f"{enrichment_bucket.bucket_arn}/*",
        #         ],
        #     )
        # )

        # ===========
        # IAM Role for Authenticated Users
        # ===========
        authenticated_role = iam.Role(
            self,
            "CognitoAuthenticatedRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": identity_pool.ref
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated"
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
            description="IAM role for authenticated Cognito users to access S3",
        )

        # Grant authenticated users S3 read on agent results bucket
        authenticated_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:ListBucket",
                ],
                resources=[
                    agent_results_bucket.bucket_arn,
                    f"{agent_results_bucket.bucket_arn}/*",
                ],
            )
        )

        # Grant authenticated users S3 read/write on enrichment bucket
        authenticated_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket",
                ],
                resources=[
                    enrichment_bucket.bucket_arn,
                    f"{enrichment_bucket.bucket_arn}/*",
                    f"arn:aws:s3:::{config['domains_config_s3_bucket']}",
                    f"arn:aws:s3:::{config['domains_config_s3_bucket']}/*",
                ],
            )
        )


        # ===========
        # Attach Roles to Identity Pool
        # ===========
        cognito.CfnIdentityPoolRoleAttachment(
            self,
            "IdentityPoolRoleAttachment",
            identity_pool_id=identity_pool.ref,
            roles={
                "authenticated": authenticated_role.role_arn,
            },
        )

        # ===========
        # Outputs for .env configuration
        # ===========
        CfnOutput(
            self,
            "UserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID for frontend .env",
            export_name="MRIUserPoolId",
        )

        CfnOutput(
            self,
            "UserPoolClientId",
            value=user_pool_client.user_pool_client_id,
            description="Cognito User Pool App Client ID for frontend .env",
            export_name="MRIUserPoolClientId",
        )

        CfnOutput(
            self,
            "IdentityPoolId",
            value=identity_pool.ref,
            description="Cognito Identity Pool ID for frontend .env",
            export_name="MRIIdentityPoolId",
        )

        CfnOutput(
            self,
            "AgentResultsS3BucketName",
            value=agent_results_bucket.bucket_name,
            description="S3 bucket name for agent results",
            export_name="AgentResultsBucketName",
        )

        CfnOutput(
            self,
            "AgentResultsS3BucketArn",
            value=agent_results_bucket.bucket_arn,
            description="S3 bucket ARN",
            export_name="AgentResultsBucketArn",
        )

        CfnOutput(
            self,
            "EnrichmentBucketName",
            value=enrichment_bucket.bucket_name,
            description="S3 bucket name for enrichment results",
            export_name="EnrichmentResultsBucketName",
        )

        CfnOutput(
            self,
            "EnrichmentBucketArn",
            value=enrichment_bucket.bucket_arn,
            description="Enrichment S3 bucket ARN",
            export_name="EnrichmentResultsBucketArn",
        )

        CfnOutput(
            self,
            "AWSRegion",
            value=self.region,
            description="AWS Region",
            export_name="MRIAWSRegion",
        )

        # CloudFront outputs
        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=distribution.distribution_id,
            description="CloudFront Distribution ID",
            export_name="MRICloudFrontDistributionId",
        )

        CfnOutput(
            self,
            "CloudFrontDomainName",
            value=distribution.distribution_domain_name,
            description="CloudFront Domain Name (Website URL)",
            export_name="MRICloudFrontDomainName",
        )

        CfnOutput(
            self,
            "WebsiteBucketName",
            value=website_bucket.bucket_name,
            description="S3 bucket for website static files",
            export_name="MRIWebsiteBucketName",
        )

        CfnOutput(
            self,
            "WebsiteURL",
            value=f"https://{distribution.distribution_domain_name}",
            description="Website URL",
            export_name="MRIWebsiteURL",
        )
