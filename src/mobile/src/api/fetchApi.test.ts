import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const auth = vi.hoisted(() => ({
  getAccessToken: vi.fn(),
  refreshAccessToken: vi.fn(),
}))
vi.mock('@/services/authService', () => auth)
vi.mock('@/api/constants', () => ({
  API_URL: 'https://api.example.test',
  BASE_URL: 'https://example.test',
}))

import { fetchApi } from './fetchApi'
import { clearRateLimits, useRateLimits } from './rateLimits'

beforeEach(() => {
  vi.clearAllMocks()
  clearRateLimits()
  auth.getAccessToken.mockResolvedValue('token')
  auth.refreshAccessToken.mockResolvedValue('refreshed')
})
afterEach(() => vi.unstubAllGlobals())

const json = (body: unknown, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })

describe('mobile API throttling', () => {
  it('shares a cooldown within a scope without sending blocked requests', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        json({ detail: 'Throttled' }, 429, { 'Retry-After': '60' })
      )
    vi.stubGlobal('fetch', fetch)
    const before = Date.now()
    await expect(
      fetchApi('/ai-jobs/a/transcript/', { rateLimitScope: 'aiResult' })
    ).rejects.toMatchObject({
      statusCode: 429,
      body: { detail: 'Throttled' },
    })
    await expect(
      fetchApi('/ai-jobs/b/summary/', { rateLimitScope: 'aiResult' })
    ).rejects.toMatchObject({
      statusCode: 429,
      message: 'Api error 429 (GET /ai-jobs/b/summary/)',
      request: { method: 'GET', path: '/ai-jobs/b/summary/' },
    })
    expect(useRateLimits.getState().cooldowns.aiResult).toBeGreaterThanOrEqual(
      before + 60_000
    )
    expect(useRateLimits.getState().hits.aiResult).toBe(1)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0][1]).not.toHaveProperty('rateLimitScope')
  })

  it('does not record or block requests without a scope', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(json({}, 429, { 'Retry-After': '60' }))
    vi.stubGlobal('fetch', fetch)
    await expect(fetchApi('/users/me/')).rejects.toMatchObject({
      statusCode: 429,
    })
    await expect(fetchApi('/files/')).rejects.toMatchObject({
      statusCode: 429,
    })
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(useRateLimits.getState().cooldowns).toEqual({})
  })

  it('handles throttling after refreshing authentication and preserves bearer headers', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response('invalid JSON', {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        })
      )
      .mockResolvedValueOnce(json({}, 429, { 'Retry-After': '60' }))
    vi.stubGlobal('fetch', fetch)
    await expect(
      fetchApi('files/', { method: 'POST', rateLimitScope: 'upload' })
    ).rejects.toMatchObject({ statusCode: 429 })
    expect(auth.refreshAccessToken).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[1][1].headers.Authorization).toBe(
      'Bearer refreshed'
    )
    expect(useRateLimits.getState().cooldowns.upload).toEqual(
      expect.any(Number)
    )
  })

  it('preserves a 429 even when its JSON body is malformed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('bad JSON', {
          status: 429,
          headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
        })
      )
    )
    await expect(
      fetchApi('/files/', { method: 'POST', rateLimitScope: 'upload' })
    ).rejects.toMatchObject({ statusCode: 429, retryAt: expect.any(Number) })
  })

  it.each([undefined, 'invalid'])(
    'allows explicit retry with a missing or invalid Retry-After (%s)',
    async (header) => {
      const fetch = vi
        .fn()
        .mockResolvedValueOnce(
          json({}, 429, header ? { 'Retry-After': header } : {})
        )
        .mockImplementation(() => Promise.resolve(json({})))
      vi.stubGlobal('fetch', fetch)
      const retry = {
        method: 'POST',
        rateLimitScope: 'transcriptionRetry' as const,
      }
      await expect(fetchApi('/ai-jobs/a/retry/', retry)).rejects.toMatchObject({
        statusCode: 429,
        retryAt: null,
      })
      await fetchApi('/ai-jobs/a/create-in-docs/', {
        method: 'POST',
        rateLimitScope: 'docsCreate',
      })
      await fetchApi('/ai-jobs/a/retry/', retry)
      expect(fetch).toHaveBeenCalledTimes(3)
    }
  )

  it('does not interpret a successful HTTP response with a quota-failed job as throttling', async () => {
    const job = {
      status: 'failed',
      failure_reason: 'RATE_LIMIT_TRANSCRIPTION_EXCEEDED',
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(job)))
    await expect(
      fetchApi('/ai-jobs/a/retry/', {
        method: 'POST',
        rateLimitScope: 'transcriptionRetry',
      })
    ).resolves.toEqual(job)
    expect(useRateLimits.getState().cooldowns).toEqual({})
  })

  it('preserves ordinary HTTP failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(json({ detail: 'error' }, 500))
    )
    await expect(fetchApi('/files/')).rejects.toMatchObject({
      statusCode: 500,
      body: { detail: 'error' },
      name: 'ApiError',
      message: 'Api error 500 (GET /files/)',
      request: { method: 'GET', path: '/files/' },
    })
  })

  it('marks redacted query parameters in the normalized method and route', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ detail: 'error' }, 403))
    vi.stubGlobal('fetch', fetch)
    await expect(
      fetchApi('files/abc/upload-ended?token=private#secret', {
        method: 'post',
        body: JSON.stringify({ title: 'Confidential recording' }),
      })
    ).rejects.toMatchObject({
      message: 'Api error 403 (POST /files/abc/upload-ended/?[redacted])',
      request: { method: 'POST', path: '/files/abc/upload-ended/?[redacted]' },
    })
    expect(fetch).toHaveBeenCalledWith(
      'https://api.example.test/files/abc/upload-ended/?token=private',
      expect.objectContaining({ method: 'post' })
    )
  })

  it('preserves request context when authentication refresh is followed by an HTTP error', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json({}, 401))
        .mockResolvedValueOnce(json({}, 500))
    )
    await expect(
      fetchApi('/files/abc/upload-ended/', { method: 'POST' })
    ).rejects.toMatchObject({
      message: 'Api error 500 (POST /files/abc/upload-ended/)',
      request: { method: 'POST', path: '/files/abc/upload-ended/' },
    })
  })
})
