import aws_cdk as core
import aws_cdk.assertions as assertions

from market_research_intelligence.market_research_intelligence_stack import MarketResearchIntelligenceStack

# example tests. To run these tests, uncomment this file along with the example
# resource in market_research_intelligence/market_research_intelligence_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = MarketResearchIntelligenceStack(app, "market-research-intelligence-prototype")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
