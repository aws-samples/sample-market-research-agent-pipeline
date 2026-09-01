import aws_cdk as cdk
from aws_cdk import Aspects
from cdk_nag import AwsSolutionsChecks, NagSuppressions

from market_research_intelligence.market_research_intelligence_stack import MarketResearchIntelligenceStack


app = cdk.App()
stack = MarketResearchIntelligenceStack(app, "MarketResearchIntelligenceStackV4",)

# Apply cdk-nag AwsSolutionsChecks to validate against AWS Solutions best practices
Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

# Add NagSuppressions for prototype-acceptable violations
NagSuppressions.add_stack_suppressions(stack, [
    {
        "id": "AwsSolutions-IAM4",
        "reason": "AWS managed policy for Lambda basic execution is acceptable for prototype"
    },
    {
        "id": "AwsSolutions-IAM5",
        "reason": "Wildcard permissions are for Lambda invoke and required by AWS services (Bedrock, Step Functions) - acceptable for prototype"
    },
    {
        "id": "AwsSolutions-L1",
        "reason": "Python 3.11 is current stable runtime for prototype"
    },
    {
        "id": "AwsSolutions-SF1",
        "reason": "Step function logging not enabled for prototype - cost consideration"
    },
    {
        "id": "AwsSolutions-SF2",
        "reason": "X-Ray tracing not enabled for prototype - cost consideration"
    },
    {
        "id": "AwsSolutions-S1",
        "reason": "S3 server access logging intentionally disabled for prototype - cost consideration"
    },
    {
        "id": "AwsSolutions-APIG2",
        "reason": "Request body validation enabled; path/query validation not needed for these POST-only endpoints"
    },
    {
        "id": "AwsSolutions-APIG3",
        "reason": "WAFv2 not required for prototype stage"
    },
])

app.synth()
