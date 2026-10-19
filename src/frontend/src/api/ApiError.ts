class ApiError extends Error {
  statusCode: number
  body: unknown
  retryAt: number | null
  constructor(
    statusCode: number,
    body: unknown,
    retryAt: number | null = null
  ) {
    super(`Api error ${statusCode}`)
    this.statusCode = statusCode
    this.body = body
    this.retryAt = retryAt
  }
}

export { ApiError }
