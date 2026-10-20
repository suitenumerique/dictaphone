import { useEffect, useState } from 'react'
import { isBlocked, type RateLimitScope, useRateLimits } from './rateLimits'

/** Rerender at expiry; no ticking live region or per-second announcements. */
export function useCooldown(scope: RateLimitScope) {
  const retryAt = useRateLimits((state) => state.cooldowns[scope])
  const [, setExpired] = useState(0)
  const blocked = isBlocked(retryAt)
  useEffect(() => {
    if (!blocked) return
    const timer = setTimeout(
      () => setExpired((count) => count + 1),
      Math.min(retryAt! - Date.now() + 50, 2_147_483_647)
    )
    return () => clearTimeout(timer)
  }, [blocked, retryAt])
  return { retryAt, isBlocked: blocked }
}
