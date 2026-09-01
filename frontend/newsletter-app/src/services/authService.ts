import { fromCognitoIdentityPool } from '@aws-sdk/credential-providers';
import { AWSConfig } from '../types/newsletter.types';
import { Amplify } from 'aws-amplify';
import {
  signIn as amplifySignIn,
  signUp as amplifySignUp,
  confirmSignUp as amplifyConfirmSignUp,
  confirmSignIn as amplifyConfirmSignIn,
  resetPassword as amplifyResetPassword,
  confirmResetPassword as amplifyConfirmResetPassword,
  signOut as amplifySignOut,
  getCurrentUser as amplifyGetCurrentUser,
  fetchAuthSession
} from 'aws-amplify/auth';

// Authentication modes
export type AuthMode = 'cognito' | 'default';

// Get AWS configuration from environment variables
export const getAWSConfig = (): AWSConfig => {
  const region = import.meta.env.VITE_AWS_REGION || 'us-east-1';
  const identityPoolId = import.meta.env.VITE_COGNITO_IDENTITY_POOL_ID || '';
  const s3Bucket = import.meta.env.VITE_S3_BUCKET || 'agent-results';
  const enrichmentKeywordsBucket = import.meta.env.VITE_ENRICHMENT_KEYWORDS_BUCKET || '';
  const domainsConfigBucket = import.meta.env.VITE_DOMAINS_CONFIG_BUCKET || '';

  return {
    region,
    identityPoolId,
    s3Bucket,
    enrichmentKeywordsBucket,
    domainsConfigBucket,
  };
};

// Determine authentication mode
export const getAuthMode = (): AuthMode => {
  const config = getAWSConfig();
  // Use Cognito if identity pool ID is provided, otherwise use default credentials
  return config.identityPoolId ? 'cognito' : 'default';
};

// Get Cognito credentials provider for unauthenticated access
export const getCognitoCredentials = () => {
  const config = getAWSConfig();

  if (!config.identityPoolId) {
    // Return undefined to use default credential chain (AWS CLI, env vars, etc.)
    return undefined;
  }

  return fromCognitoIdentityPool({
    clientConfig: { region: config.region },
    identityPoolId: config.identityPoolId,
  });
};

// Check if AWS is configured
export const isAWSConfigured = (): boolean => {
  const config = getAWSConfig();
  return !!config.s3Bucket && !!config.region;
};

// ============================================
// Cognito User Pool Authentication (for login/signup)
// ============================================

// Configure Amplify for User Pool (separate from Identity Pool)
const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID;
const userPoolClientId = import.meta.env.VITE_COGNITO_USER_POOL_CLIENT_ID;
const identityPoolId = import.meta.env.VITE_COGNITO_IDENTITY_POOL_ID;
if (userPoolId && userPoolClientId) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId,
        identityPoolId, // Link Identity Pool for S3 access
      }
    }
  });
}

// Get ID token for API Gateway authentication
export const getIdToken = async (): Promise<string | null> => {
  try {
    const session = await fetchAuthSession({ forceRefresh: false });
    return session.tokens?.idToken?.toString() || null;
  } catch (error) {
    console.error('Failed to get token:', error);
    return null;
  }
};

// Export User Pool auth functions
export {
  amplifySignIn as signIn,
  amplifySignUp as signUp,
  amplifyConfirmSignUp as confirmSignUp,
  amplifyConfirmSignIn as confirmSignIn,
  amplifyResetPassword as resetPassword,
  amplifyConfirmResetPassword as confirmResetPassword,
  amplifySignOut as signOut,
  amplifyGetCurrentUser as getCurrentUser
};
