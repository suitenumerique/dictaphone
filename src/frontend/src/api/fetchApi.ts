import { ApiError } from './ApiError'
import { apiUrl } from './apiUrl'
import {
  isBlocked,
  parseRetryAfter,
  type RateLimitScope,
  recordRateLimit,
  useRateLimits,
} from './rateLimits'

export const fetchApi = async <T = Record<string, unknown>>(
  url: string,
  {
    rateLimitScope,
    ...options
  }: RequestInit & { rateLimitScope?: RateLimitScope } = {}
): Promise<T> => {
  if (rateLimitScope) {
    // Don't send requests the server would reject anyway.
    const retryAt = useRateLimits.getState().cooldowns[rateLimitScope]
    if (isBlocked(retryAt)) throw new ApiError(429, undefined, retryAt)
  }
  const csrfToken = getCsrfToken()
  const response = await fetch(apiUrl(url), {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(!!csrfToken && { 'X-CSRFToken': csrfToken }),
      ...options.headers,
    },
  })

  const retryAt =
    response.status === 429
      ? parseRetryAfter(response.headers.get('Retry-After'))
      : null
  if (response.status === 429 && rateLimitScope) {
    recordRateLimit(rateLimitScope, retryAt)
  }

  let result = undefined as T
  try {
    if (response.status !== 204) {
      const contentType = response.headers.get('content-type') ?? ''
      if (contentType.startsWith('text/plain')) {
        result = (await response.text()) as T
      } else if (contentType.includes('application/json')) {
        result = (await response.json()) as T
      }
    }
  } catch (error) {
    // Preserve the HTTP status even when a proxy returns an invalid error body.
    if (response.ok) throw error
  }

  if (!response.ok) {
    throw new ApiError(response.status, result, retryAt)
  }
  return result
}

const getCsrfToken = () => {
  return document.cookie
    .split(';')
    .filter((cookie) => cookie.trim().startsWith('csrftoken='))
    .map((cookie) => cookie.split('=')[1])
    .pop()
}
