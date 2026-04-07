// src/services/apiClient.ts
import { getTokens, refreshAccessToken, logout } from './authService';

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

interface ApiOptions {
  method?: HttpMethod;
  body?: unknown;
  headers?: Record<string, string>;
}

async function apiFetch<T>(url: string, options: ApiOptions = {}): Promise<T> {
  const tokens = await getTokens();
  if (!tokens) throw new Error('Not authenticated');

  const { body, method = 'GET', headers = {} } = options;

  const init: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${tokens.access}`,
      ...headers,
    },
    ...(body !== undefined && { body: JSON.stringify(body) }),
  };

  let response = await fetch(url, init);

  // Access token expired → try to refresh once
  if (response.status === 401) {
    try {
      const newAccessToken = await refreshAccessToken();

      response = await fetch(url, {
        ...init,
        headers: {
          ...init.headers as Record<string, string>,
          'Authorization': `Bearer ${newAccessToken}`,
        },
      });
    } catch {
      await logout();
      throw new Error('Session expired, please log in again');
    }
  }

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export default apiFetch;