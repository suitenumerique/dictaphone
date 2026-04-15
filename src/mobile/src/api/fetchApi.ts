import { ApiError } from './ApiError';
import { getCsrfToken, getSessionCookie } from '@/services/authService';
import { API_URL, BASE_URL } from '@/api/constants';

function isModifierMethod(method?: string) {
  return ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method ?? '');
}

export const fetchApi = async <T = Record<string, unknown>>(
  url: string,
  options?: RequestInit,
): Promise<T> => {
  const sessionId = await getSessionCookie();
  const csrfToken = await getCsrfToken();

  if (!url.startsWith('/')) {
    url = `/${url}`;
  }
  let cookie = `sessionid=${sessionId}`;
  if (isModifierMethod(options?.method)) {
    cookie += `; csrftoken=${csrfToken ?? 'not_set'};`;
  }

  const response = await fetch(`${API_URL}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Cookie: cookie,
      ...(isModifierMethod(options?.method)
        ? { 'X-CSRFToken': csrfToken ?? 'not_set' }
        : {}),
      Referer: BASE_URL,
      ...options?.headers,
    },
  });

  let result: T;
  if (response.status === 204) {
    result = undefined as T;
  } else {
    const contentType = response.headers.get('content-type') ?? '';
    if (contentType === 'text/plain' || contentType.includes('text/html')) {
      result = (await response.text()) as T;
    } else if (!contentType.includes('application/json')) {
      result = undefined as T;
    } else {
      result = (await response.json()) as T;
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, result);
  }
  return result;
};
