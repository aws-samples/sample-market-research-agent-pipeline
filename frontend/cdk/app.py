import os
import aws_cdk as cdk
from aws_cdk import Aspects
from cdk_nag import AwsSolutionsChecks, NagSuppressions
from frontend_stack import FrontendStack

app = cdk.App()

stack = FrontendStack(
    app,
    "FrontendStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
    ),
    description="Frontend infrastructure: Cognito Identity Pool and S3 bucket for Market Research Intelligence App",
)

Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

# Add NagSuppressions for prototype-acceptable violations
NagSuppressions.add_stack_suppressions(stack, [
    {
        "id": "AwsSolutions-S1",
        "reason": "S3 server access logging intentionally disabled for prototype - cost consideration"
    },
    {
        "id": "AwsSolutions-CFR3",
        "reason": "CloudFront access logging intentionally disabled for prototype - cost consideration"
    },
    {
        "id": "AwsSolutions-CFR1",
        "reason": "Geo restrictions not required for this prototype"
    },
    {
        "id": "AwsSolutions-CFR2",
        "reason": "WAF not required for this prototype"
    },
    {
        "id": "AwsSolutions-CFR4",
        "reason": "Using TLS 1.2 minimum; CFR4 flags default cert which is acceptable for prototype without custom domain"
    },
    {
        "id": "AwsSolutions-CFR7",
        "reason": "Using OAI which is functionally equivalent to OAC; migration to OAC planned for production"
    },
    {
        "id": "AwsSolutions-COG2",
        "reason": "MFA not required for prototype stage; will be enabled for production"
    },
    {
        "id": "AwsSolutions-COG3",
        "reason": "AdvancedSecurityMode requires Cognito Plus pricing tier; not cost-effective for prototype"
    },
    {
        "id": "AwsSolutions-COG8",
        "reason": "Cognito Plus tier not cost-effective for prototype; will be enabled for production"
    },
    {
        "id": "AwsSolutions-IAM5",
        "reason": "Wildcard on bucket/* needed to read/write all objects within the bucket. Actions are scoped to specific S3 operations only"
    },
])

app.synth()
