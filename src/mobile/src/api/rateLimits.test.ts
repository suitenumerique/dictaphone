import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  areUploadsPaused,
  clearRateLimit,
  clearRateLimits,
  isBlocked,
  parseRetryAfter,
  recordRateLimit,
  useRateLimits,
} from './rateLimits'

beforeEach(() => {
  clearRateLimits()
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-19T12:00:00Z'))
})
afterEach(() => vi.useRealTimers())

describe('Retry-After', () => {
  it('parses seconds and HTTP dates relative to receipt time', () => {
    expect(parseRetryAfter('60')).toBe(Date.now() + 60_000)
    expect(parseRetryAfter('Mon, 19 Oct 2026 12:02:00 GMT')).toBe(
      Date.now() + 120_000
    )
    expect(parseRetryAfter('Mon, 19 Oct 2026 11:00:00 GMT')).toBe(Date.now())
  })
  it.each([
    null,
    '',
    ' ',
    '-10',
    '1.5',
    'later',
    '9'.repeat(400),
    '99999999999999',
  ])('handles missing or invalid headers: %s', (value) => {
    expect(parseRetryAfter(value)).toBeNull()
  })
})

describe('cooldowns', () => {
  const retryAt = (scope: 'aiResult' | 'upload') =>
    useRateLimits.getState().cooldowns[scope]

  it('counts every hit per scope, including unchanged retry values', () => {
    const deadline = Date.now() + 60_000
    recordRateLimit('aiResult', deadline)
    recordRateLimit('aiResult', deadline)
    recordRateLimit('aiResult', null)
    recordRateLimit('upload', null)
    recordRateLimit('upload', null)
    expect(useRateLimits.getState().hits).toEqual({ aiResult: 3, upload: 2 })
    expect(retryAt('aiResult')).toBe(deadline)
    expect(retryAt('upload')).toBeNull()
  })

  it('discards an expired stored deadline when the next hit has no Retry-After', () => {
    recordRateLimit('upload', Date.now() + 60_000)
    vi.advanceTimersByTime(60_000)
    recordRateLimit('upload', null)
    expect(retryAt('upload')).toBeNull()
    expect(areUploadsPaused()).toBe(true)
    expect(useRateLimits.getState().hits.upload).toBe(2)
  })

  it('resets cooldowns and hit counters together', () => {
    recordRateLimit('aiResult', null)
    recordRateLimit('upload', null)
    clearRateLimits()
    expect(useRateLimits.getState()).toEqual({ cooldowns: {}, hits: {} })
    recordRateLimit('upload', null)
    expect(useRateLimits.getState().hits).toEqual({ upload: 1 })
  })

  it('never shortens the wait and isolates scopes', () => {
    recordRateLimit('aiResult', Date.now() + 60_000)
    recordRateLimit('aiResult', Date.now() + 30_000)
    recordRateLimit('aiResult', null)
    expect(retryAt('aiResult')).toBe(Date.now() + 60_000)
    expect(isBlocked(retryAt('aiResult'))).toBe(true)
    expect(
      useRateLimits.getState().cooldowns.transcriptionRetry
    ).toBeUndefined()
    vi.advanceTimersByTime(60_001)
    expect(isBlocked(retryAt('aiResult'))).toBe(false)
  })
  it('does not block without a usable Retry-After', () => {
    recordRateLimit('aiResult', null)
    expect(retryAt('aiResult')).toBeNull()
    expect(isBlocked(retryAt('aiResult'))).toBe(false)
  })
  it('keeps uploads paused until explicitly resumed, even after expiry', () => {
    recordRateLimit('upload', Date.now() + 60_000)
    expect(areUploadsPaused()).toBe(true)
    vi.advanceTimersByTime(60_001)
    expect(areUploadsPaused()).toBe(true)
    clearRateLimit('upload')
    expect(areUploadsPaused()).toBe(false)
  })
})
