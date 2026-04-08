import { ApiError } from './ApiError'
import { getSessionCookie } from '@/services/authService';
import { API_URL } from '@/api/constants';

export const fetchApi = async <T = Record<string, unknown>>(
  url: string,
  options?: RequestInit
): Promise<T> => {
  const sessionId = await getSessionCookie()
  if (!url.startsWith('/')) {
    url = `/${url}`
  }
  const response = await fetch(`${API_URL}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Cookie: `sessionid=${sessionId}`,
      ...options?.headers,
    },
  });

  let result: T
  if (response.status === 204) {
    result = undefined as T
  } else {
    const contentType = response.headers.get('content-type') ?? ''
    if (contentType === 'text/plain') {
      result = (await response.text()) as T
    } else if (!contentType.includes('application/json')) {
      result = undefined as T
    } else {
      result = (await response.json()) as T
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, result)
  }
  return result
}
