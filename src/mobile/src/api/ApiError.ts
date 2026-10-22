export type ApiErrorRequest = {
  method: string
  path: string
}

class ApiError extends Error {
  statusCode: number
  body: unknown
  retryAt: number | null
  request?: ApiErrorRequest
  constructor(
    statusCode: number,
    body: unknown,
    retryAt: number | null = null,
    request?: ApiErrorRequest
  ) {
    const safeRequest = request && {
      method: request.method.toUpperCase(),
      path: request.path.split(/[?#]/, 1)[0],
    }
    super(
      `Api error ${statusCode}${safeRequest ? ` (${safeRequest.method} ${safeRequest.path})` : ''}`
    )
    this.name = 'ApiError'
    this.statusCode = statusCode
    this.body = body
    this.retryAt = retryAt
    this.request = safeRequest
  }
}

export { ApiError }
