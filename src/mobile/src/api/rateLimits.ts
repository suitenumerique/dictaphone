import { create } from 'zustand'
import { ApiError } from './ApiError'

/** Mirrors the backend throttle groups; requests opt in via `fetchApi`. */
export type RateLimitScope =
  'upload' | 'transcriptionRetry' | 'docsCreate' | 'aiResult'

/** Epoch ms until which a scope is throttled, or null without a usable Retry-After. */
export type RetryAt = number | null

export const useRateLimits = create<{
  cooldowns: Partial<Record<RateLimitScope, RetryAt>>
  hits: Partial<Record<RateLimitScope, number>>
}>(() => ({ cooldowns: {}, hits: {} }))

export const parseRetryAfter = (value: string | null, now = Date.now()) => {
  const trimmed = value?.trim()
  if (!trimmed) return null
  if (/^\d+$/.test(trimmed)) {
    const retryAt = now + Number(trimmed) * 1000
    // Beyond this, Date cannot represent the value.
    return retryAt <= 8.64e15 ? retryAt : null
  }
  // Reject malformed numeric values rather than interpreting them as dates.
  if (/^[+-]?[\d.]+$/.test(trimmed)) return null
  const date = Date.parse(trimmed)
  return Number.isFinite(date) ? Math.max(now, date) : null
}

export const isRateLimitError = (error: unknown): error is ApiError =>
  error instanceof ApiError && error.statusCode === 429

export const isBlocked = (retryAt: RetryAt | undefined) =>
  retryAt != null && retryAt > Date.now()

export const recordRateLimit = (scope: RateLimitScope, retryAt: RetryAt) =>
  useRateLimits.setState(({ cooldowns, hits }) => {
    const current = cooldowns[scope]
    // Concurrent responses never shorten the wait.
    const next =
      isBlocked(current) && current! > (retryAt ?? 0) ? current! : retryAt
    return {
      cooldowns: { ...cooldowns, [scope]: next },
      hits: { ...hits, [scope]: (hits[scope] ?? 0) + 1 },
    }
  })

export const clearRateLimit = (scope: RateLimitScope) =>
  useRateLimits.setState(({ cooldowns }) => {
    const next = { ...cooldowns }
    delete next[scope]
    return { cooldowns: next }
  })

export const clearRateLimits = () =>
  useRateLimits.setState({ cooldowns: {}, hits: {} })

/** Uploads stay paused until the user resumes them, even once the cooldown expires. */
export const areUploadsPaused = () =>
  useRateLimits.getState().cooldowns.upload !== undefined
export const useUploadsPaused = () =>
  useRateLimits((state) => state.cooldowns.upload !== undefined)
