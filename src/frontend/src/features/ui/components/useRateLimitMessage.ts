import { useTranslation } from 'react-i18next'

export function useRateLimitMessage() {
  const { t, i18n } = useTranslation('shared')
  return (retryAt: number | null) =>
    retryAt == null
      ? t('rateLimit.tryLater')
      : retryAt <= Date.now()
        ? t('rateLimit.ready')
        : t('rateLimit.waitUntil', {
            time: new Intl.DateTimeFormat(i18n.language, {
              dateStyle: 'short',
              timeStyle: 'medium',
            }).format(retryAt),
          })
}
