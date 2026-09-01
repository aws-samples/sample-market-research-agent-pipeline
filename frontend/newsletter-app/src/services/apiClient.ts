import { getIdToken } from './authService';

export const apiClient = async (url: string, options: RequestInit = {}) => {
  const idToken = await getIdToken();
  
  const headers = {
    'Content-Type': 'application/json',
    ...(idToken && { 'Authorization': `Bearer ${idToken}` }),
    ...options.headers,
  };

  return fetch(url, { ...options, headers });
};
