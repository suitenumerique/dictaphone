import { type TFunction } from 'i18next'
import { type RetryAt } from '@/api/rateLimits'

export const formatRateLimitMessage = (t: TFunction, retryAt: RetryAt) =>
  retryAt == null
    ? t('rateLimits.tryLater')
    : t('rateLimits.retryAt', {
        time: t('shared.utils.formatDateTime', {
          value: new Date(retryAt),
          includeSeconds: true,
        }),
      })
