import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchApi } from './fetchApi'
import { clearRateLimits, useRateLimits } from './rateLimits'

beforeEach(() => {
  clearRateLimits()
  vi.stubGlobal('document', { cookie: '' })
})
afterEach(() => vi.unstubAllGlobals())

describe('API throttling', () => {
  it('retains Retry-After and blocks other requests in the same scope without sending them', async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Throttled' }), {
        status: 429,
        headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
      })
    )
    vi.stubGlobal('fetch', fetch)
    const before = Date.now()
    await expect(
      fetchApi('/ai-jobs/a/transcript/', { rateLimitScope: 'aiResult' })
    ).rejects.toMatchObject({
      statusCode: 429,
      body: { detail: 'Throttled' },
    })
    expect(useRateLimits.getState().cooldowns.aiResult).toBeGreaterThanOrEqual(
      before + 60_000
    )
    await expect(
      fetchApi('/ai-jobs/b/summary/', { rateLimitScope: 'aiResult' })
    ).rejects.toMatchObject({ statusCode: 429 })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0][1]).not.toHaveProperty('rateLimitScope')
  })
  it('allows an explicit retry when the header is missing and does not affect other operations', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response('', { status: 429 }))
      .mockImplementation(() =>
        Promise.resolve(
          new Response('{}', {
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
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
  })
  it('preserves 429 metadata even with a malformed error body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('not JSON', {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': '60',
          },
        })
      )
    )
    await expect(
      fetchApi('/files/', { method: 'POST', rateLimitScope: 'upload' })
    ).rejects.toMatchObject({ statusCode: 429 })
  })
  it('does not treat a quota-failed retry response as an HTTP rate limit', async () => {
    const job = {
      id: 'retry-job',
      status: 'failed',
      failure_reason: 'RATE_LIMIT_TRANSCRIPTION_EXCEEDED',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(job), {
          headers: { 'Content-Type': 'application/json' },
        })
      )
    )
    await expect(
      fetchApi('/ai-jobs/a/retry/', {
        method: 'POST',
        rateLimitScope: 'transcriptionRetry',
      })
    ).resolves.toEqual(job)
    expect(useRateLimits.getState().cooldowns).toEqual({})
  })
  it('retains generic HTTP error handling', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('{"detail":"error"}', {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    )
    await expect(fetchApi('/files/')).rejects.toMatchObject({
      statusCode: 500,
      body: { detail: 'error' },
    })
    expect(useRateLimits.getState().cooldowns).toEqual({})
  })
})
