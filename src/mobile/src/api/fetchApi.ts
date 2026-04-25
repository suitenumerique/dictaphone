import { ApiError } from './ApiError'
import { getAccessToken, refreshAccessToken } from '@/services/authService'
import { API_URL, BASE_URL } from '@/api/constants'

function buildHeaders(
  accessToken: string | null,
  options?: RequestInit
): RequestInit['headers'] {
  return {
    'Content-Type': 'application/json',
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    Referer: BASE_URL,
    ...options?.headers,
  }
}

async function parseResponse<T>(
  response: Response
): Promise<{ response: Response; result: T }> {
  let result: T
  if (response.status === 204) {
    result = undefined as T
  } else {
    const contentType = response.headers.get('content-type') ?? ''
    if (contentType === 'text/plain' || contentType.includes('text/html')) {
      result = (await response.text()) as T
    } else if (!contentType.includes('application/json')) {
      result = undefined as T
    } else {
      result = (await response.json()) as T
    }
  }

  return { response, result }
}

export const fetchApi = async <T = Record<string, unknown>>(
  url: string,
  options?: RequestInit
): Promise<T> => {
  if (!url.startsWith('/')) {
    url = `/${url}`
  }

  const token = await getAccessToken()
  const firstResponse = await fetch(`${API_URL}${url}`, {
    ...options,
    headers: buildHeaders(token, options),
  })
  const first = await parseResponse<T>(firstResponse)

  if (first.response.status === 401) {
    const refreshedToken = await refreshAccessToken()
    if (refreshedToken) {
      const retryResponse = await fetch(`${API_URL}${url}`, {
        ...options,
        headers: buildHeaders(refreshedToken, options),
      })
      const retry = await parseResponse<T>(retryResponse)

      if (!retry.response.ok) {
        throw new ApiError(retry.response.status, retry.result)
      }
      return retry.result
    }
  }

  if (!first.response.ok) {
    throw new ApiError(first.response.status, first.result)
  }
  return first.result
}
