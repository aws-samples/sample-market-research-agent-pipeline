# Market Research Intelligence App

A React-based frontend application for viewing market research intelligence brief results produced by the orchestrator agent.

## Features

- **Topic-based Intelligence Briefs**: View news items organized by research topic (e.g., Enterprise AI, Cloud Computing)
- **Category Sections**: News items are grouped into two categories:
  - **Competitive Landscape**: Competitor moves, product launches, and strategic positioning
  - **Deals & Partnerships**: M&A activity, licensing deals, and strategic alliances
- **Rich Content Display**: Each news item includes:
  - Headline (title)
  - Keywords (as tags)
  - Summary
  - Insights
  - Implications
- **AWS Integration**: Fetches data from S3 using Cognito for authentication

## Prerequisites

- Node.js 18+ 
- npm or yarn
- AWS Account with:
  - Cognito Identity Pool configured for unauthenticated access
  - S3 bucket (`agent-results`) with appropriate CORS and permissions

## Setup

1. **Install dependencies**:
   ```bash
   cd frontend/newsletter-app
   npm install
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your AWS configuration:
   ```
   VITE_AWS_REGION=us-east-1
   VITE_COGNITO_IDENTITY_POOL_ID=us-east-1:your-identity-pool-id
   VITE_S3_BUCKET=agent-results
   ```

3. **Configure S3 CORS**:
   Your S3 bucket needs CORS configured to allow browser access:
   ```json
   [
     {
       "AllowedHeaders": ["*"],
       "AllowedMethods": ["GET", "HEAD"],
       "AllowedOrigins": ["http://localhost:5173", "https://your-domain.com"],
       "ExposeHeaders": []
     }
   ]
   ```

4. **Configure Cognito Identity Pool**:
   - Create an Identity Pool in AWS Cognito
   - Enable unauthenticated access
   - Attach an IAM role with S3 read permissions:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:GetObject",
           "s3:ListBucket"
         ],
         "Resource": [
           "arn:aws:s3:::agent-results",
           "arn:aws:s3:::agent-results/*"
         ]
       }
     ]
   }
   ```

## S3 Data Structure

The app expects data in the following S3 structure:
```
agent-results/
├── enterprise_ai/
│   ├── competitive_landscape/
│   │   ├── 2026-02-14.json
│   │   └── 2026-02-13.json
│   └── deals_and_partnerships/
│       ├── 2026-02-14.json
│       └── 2026-02-13.json
├── cloud_computing/
│   ├── competitive_landscape/
│   │   └── ...
│   └── deals_and_partnerships/
│       └── ...
```

Each JSON file should have the following structure:
```json
{
  "title": "Headline for the news item",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "summary": "A concise summary of the news...",
  "insights": "Key analytical insights...",
  "implications": "Broader implications and impact..."
}
```

## Development

Start the development server:
```bash
npm run dev
```

The app will be available at `http://localhost:5173`

## Build

Create a production build:
```bash
npm run build
```

Preview the production build:
```bash
npm run preview
```

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **Tailwind CSS** - Styling
- **AWS SDK v3** - S3 access
- **Amazon Cognito** - Authentication

## Project Structure

```
src/
├── components/
│   ├── Header.tsx           - Intelligence brief header with topic
│   ├── CategorySection.tsx  - Collapsible category sections
│   ├── NewsItemCard.tsx     - Individual news item display
│   └── LoadingSpinner.tsx   - Loading state indicator
├── services/
│   ├── authService.ts       - Cognito authentication
│   └── s3Service.ts         - S3 data fetching
├── types/
│   └── newsletter.types.ts  - TypeScript interfaces
├── App.tsx                  - Main application component
├── main.tsx                 - Entry point
└── index.css                - Tailwind CSS styles
```
