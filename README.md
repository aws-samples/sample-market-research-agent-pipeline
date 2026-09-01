# Market Research Intelligence Platform

This prototype solution allows end users to get the latest updates and AI-generated intelligence briefs on market research topics of interest. The tool aggregates news from various sources, categorizes them, and generates structured intelligence reports — including summaries, insights, and implications — tailored to specific client accounts.

The user interface is a single-page application (SPA) built using React.js and TailwindCSS.

---

## Prerequisites

- **AWS CLI** v2.x configured with credentials
- **Node.js** 18+
- **Python** 3.11+
- **AWS CDK** v2.x (`npm install -g aws-cdk`)
- **Docker** running (required for Lambda container builds and AgentCore runtime)
- **API Keys**: Crunchbase, SerpAPI, Tavily


## Configuration Files

Before deploying, you need to update the following configuration files with your own values. All placeholder values use `<YOUR_...>` format.

### 1. `backend/config.json` — Backend Infrastructure Config

This is the **primary config file**. Replace all `<YOUR_...>` placeholders:

| Field | What to Set |
|---|---|
| `AWS_REGION` | Your AWS region (e.g., `us-east-1`) |
| `API_KEYS_SECRET_ARN` | ARN of your Secrets Manager secret (created in deployment Step 1) |
| `COGNITO_USER_POOL_ARN` | Your Cognito User Pool ARN (from backend stack output) |
| `FRONTEND_URL` | Your CloudFront URL (from frontend stack output) |
| `MODEL_INFERENCE_PROFILE` | Your Bedrock inference profile ARN |
| All `<YOUR_PREFIX>-*` bucket names | Choose a prefix (e.g., `mycompany-mri`) and replace `<YOUR_PREFIX>` consistently across all bucket fields |

> **Important**: The `<YOUR_PREFIX>` must be the same across all bucket names in this file. S3 bucket names must be globally unique and ≤63 characters including any suffixes the CDK appends (e.g., `-kb`, `-vs`).

### 2. `frontend/cdk/config.json` — Frontend Infrastructure Config

| Field | What to Set |
|---|---|
| `s3_website_hosting_bucket_name` | S3 bucket for the React app (must match `<YOUR_PREFIX>` from backend config) |
| `agent_results_bucket` | Agent results bucket prefix (CDK appends account ID) |
| `enrichment_bucket` | Enrichment results bucket prefix |
| `user_pool_name`, `app_client_name`, `identity_pool_name` | Names for Cognito resources |
| `domains_config_s3_bucket` | Must match `DOMAINS_CONFIG_S3_BUCKET` in backend config |

### 3. `frontend/newsletter-app/.env` — Frontend Runtime Config

Copy `.env.example` to `.env` and fill in values from CDK stack outputs:

```bash
cp .env.example .env
```

| Variable | Source |
|---|---|
| `VITE_COGNITO_USER_POOL_ID` | FrontendStack output: `UserPoolId` |
| `VITE_COGNITO_USER_POOL_CLIENT_ID` | FrontendStack output: `UserPoolClientId` |
| `VITE_COGNITO_IDENTITY_POOL_ID` | FrontendStack output: `IdentityPoolId` |
| `VITE_S3_BUCKET` | FrontendStack output: `AgentResultsS3BucketName` |
| `VITE_ENRICHMENT_KEYWORDS_BUCKET` | FrontendStack output: `EnrichmentBucketName` |
| `VITE_AGENT_API_URL` | BackendStack output: `ApiGatewayUrl` |
| `VITE_DOMAINS_CONFIG_BUCKET` | Same as `DOMAINS_CONFIG_S3_BUCKET` in backend config |

### 4. `backend/domain_profiles/market_research.json` — Domain Profile

Defines categories, data sources, terminology, and KB mappings. No secrets — edit to customize categories and enable/disable data sources.

### 5. `backend/domain_profiles/scraper_domains.json` — Scraper Config

Defines which domains the scraper targets. Edit to add/remove news sources.

---

## Deployment Steps

### 1. Create Secrets Manager Secret

All API keys are stored in a single Secrets Manager secret and fetched by Lambdas at runtime.

```bash
aws secretsmanager create-secret \
  --name market-research-intelligence/api-keys \
  --secret-string '{"SERPAPI_KEY":"<key>","TAVILYAPI_KEY":"<key>","CRUNCHBASE_USER_KEY":"<key>"}'
```

Copy the ARN from the output and set it in `backend/config.json`:
```json
"API_KEYS_SECRET_ARN": "<your-secret-arn>"
```

### 2. Deploy Backend CDK Stack

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap aws://<ACCOUNT_ID>/us-east-1   # if first time
cdk deploy MarketResearchIntelligenceStackV4 --require-approval broadening
```

Note the `ApiGatewayUrl` from the stack outputs.

### 3. Upload Configuration Files to S3

```bash
aws s3 cp backend/domain_profiles/market_research.json \
  s3://<YOUR_PREFIX>-data-sources/domain_profiles/market_research.json
aws s3 cp backend/domain_profiles/scraper_domains.json \
  s3://<YOUR_PREFIX>-data-sources/scraper_domains/scraper_domains.json
```

### 4. Sync Knowledge Bases

Upload documents to the KB source buckets (see [Knowledge Bases](#knowledge-bases) section), then sync each KB in the **Amazon Bedrock Console → Knowledge Bases → Select KB → Sync**.

### 5. Deploy Frontend CDK Stack

```bash
cd frontend/cdk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk deploy FrontendStack --require-approval broadening
```

Note the outputs: `UserPoolId`, `UserPoolClientId`, `IdentityPoolId`, `CloudFrontDomainName`, `AgentResultsS3BucketName`, `EnrichmentBucketName`.

### 6. Configure and Deploy Frontend App

```bash
cd frontend/newsletter-app
```

Edit `.env` with the outputs from Steps 2 and 5:
```env
VITE_AWS_REGION=us-east-1
VITE_COGNITO_USER_POOL_ID=<from Step 5>
VITE_COGNITO_USER_POOL_CLIENT_ID=<from Step 5>
VITE_COGNITO_IDENTITY_POOL_ID=<from Step 5>
VITE_S3_BUCKET=<from Step 5: AgentResultsS3BucketName>
VITE_ENRICHMENT_KEYWORDS_BUCKET=<from Step 5: EnrichmentBucketName>
VITE_AGENT_API_URL=<from Step 2: ApiGatewayUrl>
VITE_DOMAINS_CONFIG_BUCKET=<YOUR_PREFIX>-data-sources
```

Build and deploy:
```bash
npm install && npm run build
cd ..
chmod +x deploy.sh && ./deploy.sh
```

### 7. Create a Cognito User

```bash
aws cognito-idp admin-create-user \
  --user-pool-id <UserPoolId> \
  --username your@email.com \
  --user-attributes Name=email,Value=your@email.com \
  --temporary-password 'TempPass123!'
```

### 8. Verify

Navigate to `https://<CloudFrontDomainName>`, sign in, and create a research topic to trigger the pipeline end-to-end.

---

## Accessing the Application

1. **Find the URL**: The tool is hosted on CloudFront. You can find the URL in the output of the `FrontendStack` deployment under the key `CloudFrontDomainName`.
2. **Authentication**: Upon visiting the URL, you will be prompted to sign in. 
   - You must first create a user inside the Cognito User Pool (providing an email and password).
   - Upon your first sign-in, you will be required to change your password.
3. **Dashboard**: After authenticating, you will land on the main dashboard, which displays all previously generated intelligence briefs fetched directly from the results S3 bucket.

---

## User Guide: Generating Intelligence Briefs

To generate a new intelligence brief, follow these steps:

1. Click the **"+ Generate"** button located in the top-right corner of the header.
2. Fill out the request form with the following details:

    *   **Research Topic**: Enter a market segment, industry, or competitive arena (e.g., Cloud Computing, Enterprise AI, Cybersecurity). 
        * *Note: Provide only one research topic per request to ensure accurate search taxonomy and relevant results.*
    *   **Client Account**: Enter the target client name (e.g., Acme Corp, TechStart Inc).
        * *Note: Provide only one client per request so the system can effectively retrieve and utilize that specific client's historical data.*
    *   **Search Taxonomy**: Upload a `.txt` file containing related keywords formatted as a JSON array of strings. Example for enterprise AI:
        ```json
        [
            "Large language models",
            "AI agents",
            "Foundation models",
            "Generative AI",
            "AI infrastructure",
            "MLOps"
        ]
        ```
    *   **KITs and KIQs (Optional)**: Key Intelligence Topics and Questions to refine the search. For example, enter "Competitive Landscape" if you only want competitive-focused data.
    *   **Execution Strategy Timeline**:
        *   **On Demand**: The backend pipeline runs immediately. You must provide a **Fetch News From Date** to define the search window. Results typically take 4-8 minutes.
        *   **Scheduler**: The pipeline runs at defined intervals. Choose a frequency (*Daily*, *Weekly* + Day of Week, or *Monthly* + Day of Month) and an execution time. This creates a cron-job scheduler in the backend.

3. Click **Generate Project** to submit your request.

---

## Viewing Outputs & Regenerating Insights

Since this is a prototype, outputs are fetched directly from S3 rather than a database. 

1. **Viewing Folders**: Once a pipeline finishes (allow 4-8 minutes), refresh the page. You will see a new folder in the left sidebar.
   * *On-Demand Example*: `Enterprise AI - 12 Mar 2026, 5:00 PM IST`
   * *Scheduled Example*: `Cloud Computing - Scheduled Weekly (Friday) - 13 Mar 2026, 6:00 PM IST`
2. **Reviewing Content**: Click the folder to view the generated intelligence briefs. Briefs are grouped into two categories: **Competitive Landscape** and **Deals & Partnerships**.
3. **No Records Found**: If the backend finds no relevant news within the requested timeframe, the UI will display a summary stating that no records were found.
4. **Regenerating Content**: You can selectively regenerate the AI's *Insights* or *Implications*:
   * Click **"Ask about insights"** or **"Ask about implications"** beneath an intelligence brief item.
   * Enter a custom prompt instructing the AI on how to adjust the output.
   * Click **Submit**.
   * The UI will display a **"Regenerating..."** spinner and automatically poll S3 until the updated content is ready — no manual refresh needed.

---

## Administration & Configuration

### Managing Client Data & Historical Knowledge
Documents such as client profiles, market benchmark reports, and historical intelligence briefs must be manually uploaded to their respective S3 buckets in the backend. An automated pipeline will extract and ingest them into Amazon Bedrock Knowledge Bases.

**S3 Buckets for Knowledge Bases**:
- `<YOUR_PREFIX>-client-data` — Client-specific intelligence (portfolios, strategies, engagement history)
- `<YOUR_PREFIX>-market-benchmark-data` — Market benchmarks, industry reports, analyst research
- `<YOUR_PREFIX>-historical-data` — Previously generated intelligence reports

**Important Metadata Step**: To ensure accurate retrieval, you must provide a metadata file for every uploaded document. For example, if the file in the Knowledge Base source bucket looks like `acme-corp-client-data.md`, you must also upload a `acme-corp-client-data.md.metadata.json` file in the same location containing:
```json
{
    "metadataAttributes": { 
        "customer": "acme corp"
    }
}
```
*Read more about Metadata Filtering in Bedrock Knowledge Bases [here](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-knowledge-bases-now-supports-metadata-filtering-to-improve-retrieval-accuracy/).*

### Configuring Search Domains
The system restricts its web searches to specific allowed domains via JSON-formatted configuration files located in the domain config S3 bucket. You can edit these files in S3 to add or remove sources.

Domain configuration is used in two places:

**1. Backend Lambdas** — S3 URIs must be specified in `backend/config.json`:

```json
{
    "DOMAINS_CONFIG_S3_URI": "s3://<YOUR_PREFIX>-data-sources/domains",
    "PRESS_RELEASE_CONFIG_S3_URI": "s3://<YOUR_PREFIX>-data-sources/press_releases",
    "SCRAPER_DOMAINS_S3_URI": "s3://<YOUR_PREFIX>-data-sources/scraper_domains"
}
```

**2. Frontend (Create Project Modal)** — The frontend also reads domain configuration at runtime from a dedicated S3 bucket to populate the domain list shown in the UI. Set the `VITE_DOMAINS_CONFIG_BUCKET` environment variable in `frontend/newsletter-app/.env` to the name of this bucket:

```env
VITE_DOMAINS_CONFIG_BUCKET=<YOUR_PREFIX>-data-sources
```

> Crunchbase (`crunchbase.com`) is automatically appended to the domain list at runtime and does not need to be listed in the config files.

Below is the expected structure for these configuration files:

**Web Search Domains** (`domains`):
```json
{
  "domains": [
    "reuters.com/business",
    "bloomberg.com",
    "techcrunch.com",
    "forbes.com/business"
  ]
}
```

**Press Release Domains** (`press_releases`):
```json
{
  "domains": [
    "https://www.reuters.com/business",
    "https://techcrunch.com",
    "https://www.bloomberg.com/markets",
    "https://www.cnbc.com/world"
  ]
}
```

**Domain Scraper Config** (`scraper_domains`):
```json
{
  "domains": ["reuters.com/business", "techcrunch.com", "venturebeat.com"],
  "url_patterns": [
    {"inurl": "/article/", "exclude": "/video/"},
    {"inurl": "/news/", "exclude": "/opinion/"}
  ],
  "excluded_domains": ["forms.google.com", "linkedin.com"],
  "excluded_paths": ["forum", "login", "signup", "podcast"]
}
```

### Backend Capabilities (config.json)
You can fine-tune backend behaviors by modifying `backend/config.json` before deploying the CDK stack:

*   **API Limits**:
    *   `MAX_TOKENS_PER_PAGE` (default `500`): Used by the Perplexity API for web searches.
    *   `MAX_RESULTS` (default `5`): Used by the Perplexity API.
    *   `PAGINATION_SERP` (default `1`): Number of pages the SerpAPI should traverse.
*   **Deal Intelligence (Crunchbase)**:
    *   `DATA_SOURCE_API_URL`: Crunchbase API endpoint (default: `https://api.crunchbase.com/api/v4/searches/organizations`)
    *   `DATA_SOURCE_TYPE`: API type — `crunchbase` or `generic`
    *   `DEAL_INTELLIGENCE_PAGE_SIZE` (default `25`): Results per API page
    *   `DEAL_INTELLIGENCE_MAX_PAGES` (default `5`): Max pages to fetch
*   **Deduplication**:
    *   `COSINE_SIMILARITY_THRESHOLD` (default `0.85`): News items with a similarity score above this threshold are flagged as duplicates and merged.

---

## Agent Architecture

The AI pipeline runs in **three sequential stages** per news item:

| Stage | Mode | Tools Used | Output |
|---|---|---|---|
| 1 | `full` | `read_s3_content` only | `summary`, `title`, `keywords` |
| 2 | `insights-implications` | All 3 KB tools (concurrent) + `read_s3_content` | `insights`, `implications` |
| 3 | `regenerate` *(on demand)* | KB tools (if needed) + `read_s3_content` | Single regenerated field |

**Stage 2 — Concurrent KB Retrieval**: The sub-agents (`CompetitiveLandscapeAgent`, `DealsPartnershipsAgent`) call all three Knowledge Base tools — `query_knowledge_customer_data`, `query_knowledge_syndicate_data`, and `query_knowledge_historical_data` — concurrently, significantly reducing latency for insights and implications generation.

**Orchestration**: The `OrchestratorAgent` routes each request to the appropriate sub-agent based on the `category` field (`competitive_landscape` → `CompetitiveLandscapeAgent`, `deals_and_partnerships` → `DealsPartnershipsAgent`).

**Prompt System**: Agent prompts are built from a template + overlay system:
- **Base templates** (`prompt_templates/base_*.txt`) define the structural skeleton shared across all categories
- **Category overlays** (`prompt_templates/overlays/*.json`) inject category-specific content (title patterns, summary structure, insight frameworks)
- **Adding a new category** requires only: a new overlay JSON + a new agent file + a registry entry in `domain_profiles/market_research.json`

### Data Ingestion Pipeline

| Lambda | Purpose |
|--------|---------|
| `enrichment_lambda` | Enriches search queries with user-provided taxonomy keywords |
| `web_search_lambda` | Searches configured domains via Perplexity API |
| `press_release_lambda` | Scrapes press release pages via SerpAPI + Tavily |
| `domain_scraper_lambda` | Configurable domain-specific content scraper (SERP + Tavily) |
| `api_connector_lambda` | Structured API data fetcher (Crunchbase / generic REST) |
| `de_duplication_merge_lambda` | Deduplicates and merges similar news items |
| `categorization_layer_lambda` | LLM-based classification into Competitive Landscape / Deals & Partnerships |
| `invoke_agent_lambda` | Invokes the AI orchestrator agent for analysis |
| `no_records_lambda` | Writes placeholder files when no news is found |
| `api_handler_lambda` | API Gateway handler for frontend requests |

### Knowledge Bases

| Knowledge Base | S3 Bucket | Purpose |
|----------------|-----------|---------|
| Client Intelligence KB | `<YOUR_PREFIX>-client-data` | Client-specific intelligence — portfolios, strategies, engagement history |
| Market Benchmark KB | `<YOUR_PREFIX>-market-benchmark-data` | Industry reports, analyst research, market benchmarks |
| Historical Intelligence KB | `<YOUR_PREFIX>-historical-data` | Previously generated reports for continuity and trend identification |

### Domain Profile Configuration

The platform is driven by a domain profile (`backend/domain_profiles/market_research.json`) that defines:
- **Categories**: Which intelligence categories are enabled and their agent mappings
- **Data Sources**: Which ingestion connectors are active
- **Terminology**: UI labels (Research Topic, Client Account, Intelligence Brief, etc.)
- **Knowledge Bases**: KB environment variable mappings and metadata filter keys

Adding a new intelligence category requires zero code changes — just add a category entry to the profile, create an agent file, and add a prompt overlay.
