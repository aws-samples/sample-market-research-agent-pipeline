interface ImportMetaEnv {
  readonly VITE_AWS_REGION: string;
  readonly VITE_COGNITO_IDENTITY_POOL_ID: string;
  readonly VITE_COGNITO_USER_POOL_ID: string;
  readonly VITE_COGNITO_USER_POOL_CLIENT_ID: string;
  readonly VITE_S3_BUCKET: string;
  readonly VITE_AGENT_API_URL: string;
  readonly VITE_ENRICHMENT_KEYWORDS_BUCKET: string;
  readonly VITE_DOMAINS_CONFIG_BUCKET: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
