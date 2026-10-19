import { Button } from '@gouvfr-lasuite/ui-components'
import { useTranslation } from 'react-i18next'
import { clearRateLimit, useUploadsPaused } from '@/api/rateLimits'
import { useCooldown } from '@/api/useCooldown'
import { useRateLimitMessage } from '@/features/ui/components/useRateLimitMessage'
import { resumeLocalUploads } from '@/features/recordings/store/useLocalRecordingsStore'
import { runImportUploads, useImportUploads } from '../importUploads'

export function UploadRateLimitAlert() {
  const { t } = useTranslation('upload')
  const paused = useUploadsPaused()
  const hasImports = useImportUploads((state) =>
    Object.values(state.filesMeta).some((file) => file.status === 'queued')
  )
  const { retryAt, isBlocked } = useCooldown('upload')
  const message = useRateLimitMessage()
  if (!paused) return null
  return (
    <div className="limit-alert" role="alert">
      <strong>{t('rateLimit.title')}</strong>
      <p>{message(retryAt ?? null)}</p>
      {hasImports && <p>{t('rateLimit.keepOpen')}</p>}
      <Button
        size="small"
        variant="secondary"
        disabled={isBlocked}
        onClick={() => {
          clearRateLimit('upload')
          resumeLocalUploads()
          void runImportUploads()
        }}
      >
        {t('rateLimit.resume')}
      </Button>
    </div>
  )
}
