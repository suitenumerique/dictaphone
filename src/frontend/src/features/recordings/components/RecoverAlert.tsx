import { useRecordingController } from '@/features/recordings/hooks/useRecordingController'
import { ProgressBar } from '@/components/ProgressBar'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { useTranslation } from 'react-i18next'
import { useCallback, useState } from 'react'

export function RecoverAlert() {
  const { t } = useTranslation(['recordings', 'record'])
  const {
    hasRecoverableRecording,
    isUploading,
    uploadProgress,
    uploadError,
    uploadCurrentRecording,
    clearRecoverableRecording,
  } = useRecordingController()

  const [isClearing, setIsClearing] = useState(false)
  const handleClear = useCallback(async () => {
    setIsClearing(true)
    try {
      await clearRecoverableRecording()
    } finally {
      setIsClearing(false)
    }
  }, [clearRecoverableRecording])

  if (!hasRecoverableRecording) return null
  return (
    <div className="recordings-recovery-alert" role="alert">
      <div className="recordings-recovery-alert__icon">
        <span className="material-icons">restore</span>
      </div>
      <div className="recordings-recovery-alert__content">
        <p className="recordings-recovery-alert__title">
          {t('record:recovery.title')}
        </p>
        <p className="recordings-recovery-alert__description">
          {t('record:recovery.description')}
        </p>
        {isUploading && (
          <ProgressBar value={uploadProgress} minValue={0} maxValue={100} />
        )}
        {uploadError && (
          <p className="recordings-recovery-alert__error">{uploadError}</p>
        )}

        <div className="recordings-recovery-alert__actions">
          <Button
            color="neutral"
            variant="secondary"
            onClick={handleClear}
            disabled={isUploading || isClearing}
            icon={<span className="material-icons">delete</span>}
          >
            {t('record:discardRecording')}
          </Button>
          <Button
            color="brand"
            onClick={uploadCurrentRecording}
            disabled={isUploading || isClearing}
            icon={<span className="material-icons">cloud_upload</span>}
          >
            {t('record:uploadCta')}
          </Button>
        </div>
      </div>
    </div>
  )
}
