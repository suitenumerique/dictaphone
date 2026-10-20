import { useEffect } from 'react'
import { Alert } from 'react-native'
import { useTranslation } from 'react-i18next'
import { type RateLimitScope, useRateLimits } from '@/api/rateLimits'
import { formatRateLimitMessage } from './rateLimitMessage'

/** A single owner notifies about every 429 response, whichever request got it. */
export function RateLimitNotifications() {
  const { t } = useTranslation()
  useEffect(
    () =>
      useRateLimits.subscribe(({ cooldowns, hits }, previous) => {
        for (const scope of Object.keys(hits) as RateLimitScope[]) {
          if (hits[scope] === previous.hits[scope]) continue
          Alert.alert(
            t('rateLimits.title'),
            formatRateLimitMessage(t, cooldowns[scope] ?? null)
          )
        }
      }),
    [t]
  )
  return null
}
