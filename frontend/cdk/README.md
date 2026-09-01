# Frontend CDK Infrastructure

This CDK stack deploys the AWS infrastructure required for the Market Research Intelligence frontend:

- **S3 Bucket** — Static website hosting for the React SPA
- **CloudFront Distribution** — CDN with HTTPS, SPA routing (404→index.html)
- **Cognito User Pool** — Email/password authentication
- **Cognito Identity Pool** — Provides authenticated users with temporary AWS credentials for direct S3 access
- **S3 Buckets (Agent Results & Enrichment)** — With CORS enabled for browser access

## Prerequisites

- Python 3.11+
- AWS CDK CLI (`npm install -g aws-cdk`)
- AWS CLI configured with credentials

## Configuration

Edit `config.json` before deploying. Replace all `<YOUR_PREFIX>` placeholders with your chosen bucket prefix:

```json
{
    "s3_website_hosting_bucket_name": "<YOUR_PREFIX>-frontend-website-bucket",
    "agent_results_bucket": "<YOUR_PREFIX>-agent-results",
    "enrichment_bucket": "<YOUR_PREFIX>-enrichment-results",
    "domains_config_s3_bucket": "<YOUR_PREFIX>-data-sources",
    ...
}
```

## Setup & Deploy

```bash
cd frontend/cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap   # first time only
cdk deploy FrontendStack --require-approval broadening
```

## Outputs

After deployment, note these values for the frontend `.env`:

```
FrontendStack.UserPoolId = us-east-1_XXXXXXX
FrontendStack.UserPoolClientId = XXXXXXXXXXXXXXXX
FrontendStack.IdentityPoolId = us-east-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
FrontendStack.CloudFrontDomainName = dXXXXXXXXXXXX.cloudfront.net
FrontendStack.AgentResultsS3BucketName = <prefix>-agent-results-<account_id>
FrontendStack.EnrichmentBucketName = <prefix>-enrichment-results-<account_id>
```

## Configure Frontend App

Copy `.env.example` to `.env` in `frontend/newsletter-app/` and fill in the values from the outputs above:

```bash
cp ../newsletter-app/.env.example ../newsletter-app/.env
```

See the root README for the full list of environment variables and their sources.

## S3 Data Structure

Agent results are stored in S3 with this structure:

```
<agent-results-bucket>/
├── enterprise_ai/
│   ├── competitive_landscape/
│   │   └── 2026-03-15.json
│   └── deals_and_partnerships/
│       └── 2026-03-15.json
├── cloud_computing/
│   ├── competitive_landscape/
│   └── deals_and_partnerships/
```

Each JSON file contains:
```json
{
  "title": "News headline",
  "keywords": ["keyword1", "keyword2"],
  "summary": "Summary text...",
  "insights": "Insights text...",
  "implications": "Implications text..."
}
```

## Destroy

To remove all resources:
```bash
cdk destroy FrontendStack
```
