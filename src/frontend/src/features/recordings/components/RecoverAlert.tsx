import { useRecordingController } from '@/features/recordings/hooks/useRecordingController'
import { ProgressBar } from '@/components/ProgressBar'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { useTranslation } from 'react-i18next'
import { useCallback, useEffect, useState } from 'react'

export function RecoverAlert() {
  const { t } = useTranslation(['recordings', 'record'])
  const {
    hasRecoverableRecording,
    recoverableRecording,
    isUploading,
    uploadProgress,
    uploadError,
    uploadCurrentRecording,
    clearRecoverableRecording,
  } = useRecordingController()

  const [pendingAction, setPendingAction] = useState<'clear' | 'upload' | null>(
    null
  )
  const [dismissedRecordingId, setDismissedRecordingId] = useState<
    string | null
  >(null)
  const currentRecoverableRecordingId = recoverableRecording?.id ?? null

  useEffect(() => {
    if (!currentRecoverableRecordingId) {
      setDismissedRecordingId(null)
    }
  }, [currentRecoverableRecordingId])

  const isDismissed =
    currentRecoverableRecordingId !== null &&
    dismissedRecordingId === currentRecoverableRecordingId

  const handleClear = useCallback(async () => {
    if (
      !currentRecoverableRecordingId ||
      pendingAction !== null ||
      isUploading
    ) {
      return
    }

    setPendingAction('clear')
    try {
      await clearRecoverableRecording(currentRecoverableRecordingId)
      setDismissedRecordingId(currentRecoverableRecordingId)
    } finally {
      setPendingAction(null)
    }
  }, [
    clearRecoverableRecording,
    currentRecoverableRecordingId,
    isUploading,
    pendingAction,
  ])

  const handleUpload = useCallback(async () => {
    if (
      !currentRecoverableRecordingId ||
      pendingAction !== null ||
      isUploading
    ) {
      return
    }

    setPendingAction('upload')
    try {
      const uploadedFile = await uploadCurrentRecording(
        currentRecoverableRecordingId
      )
      if (uploadedFile) {
        setDismissedRecordingId(currentRecoverableRecordingId)
      }
    } finally {
      setPendingAction(null)
    }
  }, [
    currentRecoverableRecordingId,
    isUploading,
    pendingAction,
    uploadCurrentRecording,
  ])

  if (!hasRecoverableRecording || isDismissed) return null
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
            onClick={() => void handleClear()}
            disabled={isUploading || pendingAction !== null}
            icon={<span className="material-icons">delete</span>}
          >
            {t('record:discardRecording')}
          </Button>
          <Button
            color="brand"
            onClick={() => void handleUpload()}
            disabled={isUploading || pendingAction !== null}
            icon={<span className="material-icons">cloud_upload</span>}
          >
            {t('record:uploadCta')}
          </Button>
        </div>
      </div>
    </div>
  )
}
