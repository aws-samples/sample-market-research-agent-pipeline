import { apiClient } from './apiClient';

// Agent API configuration from environment variables
const AGENT_API_URL = import.meta.env.VITE_AGENT_API_URL
  ? `${import.meta.env.VITE_AGENT_API_URL}/invoke-agent`
  : '';

const CREATE_PROJECT_API_URL = import.meta.env.VITE_AGENT_API_URL
  ? `${import.meta.env.VITE_AGENT_API_URL}/create-project`
  : '';

// Interface for regenerate request (matches Lambda regenerate mode)
export interface AgentRegenerateRequest {
  s3_uri: string;  // S3 URI of the existing result JSON (s3://bucket/key)
  field: 'insights' | 'implications';
  user_instruction: string;  // User's regeneration prompt
}

// Interface for agent response
export interface AgentResponse {
  success: boolean;
  response: any;  // The full regenerated result
  output_s3_uri?: string;  // S3 URI of the new result
  error?: string;
}

// Invoke the agent in regenerate mode via API Gateway
// Sends the new payload format with nested regenerate object
export const regenerateWithAgent = async (
  request: AgentRegenerateRequest
): Promise<AgentResponse> => {
  // Validate API configuration
  if (!AGENT_API_URL) {
    console.error('Agent API URL not configured. Please set VITE_AGENT_API_URL in .env');
    return {
      success: false,
      response: null,
      error: 'Agent API not configured. Please contact administrator.',
    };
  }

  try {
    // Build the payload with nested regenerate object
    const payload = {
      s3_uri: request.s3_uri,
      mode: 'regenerate',
      regenerate: {
        field: request.field,
        user_instruction: request.user_instruction,
      },
    };

    console.log('Invoking agent regenerate mode via API Gateway:', {
      apiUrl: AGENT_API_URL,
      payload: payload,
    });

    const response = await apiClient(AGENT_API_URL, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    if (!response.ok && response.status !== 202) {
      const errorText = await response.text();
      console.error('API Gateway error:', response.status, errorText);
      return {
        success: false,
        response: null,
        error: `API error: ${response.status} - ${errorText}`,
      };
    }

    const data = await response.json();
    console.log('Agent API response received:', data);

    if (response.status === 202 || data.success) {
      return {
        success: true,
        response: data.response || data,
        output_s3_uri: data.output_s3_uri,
      };
    } else {
      return {
        success: false,
        response: null,
        error: data.error || 'Unknown error from agent',
      };
    }
  } catch (error) {
    console.error('Error invoking agent regenerate:', error);
    return {
      success: false,
      response: null,
      error: error instanceof Error ? error.message : 'Network error occurred',
    };
  }
};

// Simpler function for quick regeneration
export const askAgentToRegenerate = async (
  s3Uri: string,
  field: 'insights' | 'implications',
  userInstruction: string
): Promise<AgentResponse> => {
  return regenerateWithAgent({
    s3_uri: s3Uri,
    field,
    user_instruction: userInstruction,
  });
};

export const generateInsightsImplications = async (
  s3Uri: string
): Promise<AgentResponse> => {
  if (!AGENT_API_URL) {
    console.error('Agent API URL not configured. Please set VITE_AGENT_API_URL in .env');
    return {
      success: false,
      response: null,
      error: 'Agent API not configured. Please contact administrator.',
    };
  }

  try {
    const payload = {
      s3_uri: s3Uri,
      mode: 'insights-implications',
    };

    console.log('Invoking agent generate insights/implications mode via API Gateway:', {
      apiUrl: AGENT_API_URL,
      payload: payload,
    });

    const response = await apiClient(AGENT_API_URL, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    if (!response.ok && response.status !== 202) {
      const errorText = await response.text();
      console.error('API Gateway error:', response.status, errorText);
      return {
        success: false,
        response: null,
        error: `API error: ${response.status} - ${errorText}`,
      };
    }

    const data = await response.json();
    console.log('Agent API response received:', data);

    if (response.status === 202 || data.success) {
      return {
        success: true,
        response: data.response || data,
        output_s3_uri: data.output_s3_uri,
      };
    } else {
      return {
        success: false,
        response: null,
        error: data.error || 'Unknown error from agent',
      };
    }
  } catch (error) {
    console.error('Error invoking agent:', error);
    return {
      success: false,
      response: null,
      error: error instanceof Error ? error.message : 'Network error occurred',
    };
  }
};


// Interface for create project request
export interface CreateProjectRequest {
  research_topic: string[];
  enrichment_bucket: string;
  enrichment_key: string;
  customer: string;
  category: string[];
  type: string;
}

// Create project via API Gateway
export const createProject = async (
  request: CreateProjectRequest
): Promise<AgentResponse> => {
  if (!CREATE_PROJECT_API_URL) {
    console.error('Create Project API URL not configured');
    return {
      success: false,
      response: null,
      error: 'Create Project API not configured',
    };
  }

  try {
    console.log('Creating project via API Gateway:', {
      apiUrl: CREATE_PROJECT_API_URL,
      payload: request,
    });

    const response = await apiClient(CREATE_PROJECT_API_URL, {
      method: 'POST',
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('API Gateway error:', response.status, errorText);
      return {
        success: false,
        response: null,
        error: `API error: ${response.status} - ${errorText}`,
      };
    }

    const data = await response.json();
    console.log('Create Project API response:', data);

    return {
      success: true,
      response: data,
    };
  } catch (error) {
    console.error('Error creating project:', error);
    return {
      success: false,
      response: null,
      error: error instanceof Error ? error.message : 'Network error occurred',
    };
  }
};
