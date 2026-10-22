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
    // fetchApi passes the normalized method and the path with any query string redacted.
    super(
      `Api error ${statusCode}${request ? ` (${request.method} ${request.path})` : ''}`
    )
    this.name = 'ApiError'
    this.statusCode = statusCode
    this.body = body
    this.retryAt = retryAt
    this.request = request
  }
}

export { ApiError }
