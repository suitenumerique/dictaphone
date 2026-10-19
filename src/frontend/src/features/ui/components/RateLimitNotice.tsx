import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@gouvfr-lasuite/ui-components'
import {
  isRateLimitError,
  type RateLimitScope,
  useRateLimits,
} from '@/api/rateLimits'
import { useCooldown } from '@/api/useCooldown'
import { useRateLimitMessage } from './useRateLimitMessage'
import { addToast, ToasterItem } from './toaster/Toaster'

/** A single owner notifies about every 429 response, whichever request got it. */
export function RateLimitNotifications() {
  const { t } = useTranslation('shared')
  const message = useRateLimitMessage()
  useEffect(
    () =>
      useRateLimits.subscribe(({ cooldowns, hits }, previous) => {
        const scopes = Object.keys(cooldowns) as RateLimitScope[]
        for (const scope of scopes) {
          const retryAt = cooldowns[scope]!
          if (hits[scope] === previous.hits[scope]) continue
          addToast(
            <ToasterItem type="error" closeButton>
              <span>
                {t(`rateLimit.scopes.${scope}`)} {message(retryAt)}
              </span>
            </ToasterItem>
          )
        }
      }),
    [message, t]
  )
  return null
}

/** Rate-limit errors already get a dedicated notification. */
// eslint-disable-next-line react-refresh/only-export-components
export const addErrorToast = (error: unknown, message: string) => {
  if (isRateLimitError(error)) return
  addToast(<ToasterItem type="error">{message}</ToasterItem>)
}

/**
 * Shown while the scope is blocked. With `onRetry`, it also stays once the
 * cooldown ends, to offer a retry.
 */
export function RateLimitNotice({
  scope,
  onRetry,
}: {
  scope: RateLimitScope
  onRetry?: () => void
}) {
  const { t } = useTranslation('shared')
  const { retryAt, isBlocked } = useCooldown(scope)
  const message = useRateLimitMessage()
  if (!isBlocked && !onRetry) return null
  return (
    <div className="limit-alert" role="alert">
      <strong>{t(`rateLimit.scopes.${scope}`)}</strong>
      <p>{message(retryAt ?? null)}</p>
      {onRetry && (
        <Button
          size="small"
          variant="secondary"
          disabled={isBlocked}
          onClick={onRetry}
        >
          {t('rateLimit.retry')}
        </Button>
      )}
    </div>
  )
}
