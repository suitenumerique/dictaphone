import { ProgressBar } from '@/components/ProgressBar.tsx'
import { SignalLevelMeter } from '@/features/recordings/components/SignalLevelMeter.tsx'
import { useRecordingController } from '@/features/recordings/hooks/useRecordingController.ts'
import { useDisablePageRefresh } from '@/hooks/disablePageRegresh.ts'
import {
  Button,
  Modal,
  ModalSize,
  Select,
} from '@gouvfr-lasuite/cunningham-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'wouter'

const formatDuration = (durationMs: number) => {
  const totalSeconds = Math.floor(durationMs / 1000)
  const hours = Math.floor(totalSeconds / 60 / 60)
  const minutes = Math.floor(totalSeconds / 60) % 60
  const seconds = totalSeconds % 60

  const minutesSeconds = `${String(minutes).padStart(2, '0')}:${String(
    seconds
  ).padStart(2, '0')}`
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${minutesSeconds}`
  }
  return minutesSeconds
}

const maxUploadAttempts = 2

const downloadFile = (file: File) => {
  const objectUrl = URL.createObjectURL(file)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = file.name
  link.style.display = 'none'

  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10000)
}

export default function RecordComponent() {
  const { t } = useTranslation(['record'])
  const [isStopDialogOpen, setIsStopDialogOpen] = useState(false)
  const [uploadAttempts, setUploadAttempts] = useState(0)
  const wakeLockRef = useRef<WakeLockSentinel | null>(null)

  const {
    recorderState,
    selectedAudioInputId,
    audioInputs,
    recordingDurationMs,
    analyserNode,
    uploadProgress,
    uploadError,
    recordingError,
    isUploading,
    isPaused,
    canPauseOrStop,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    switchAudioInput,
    uploadCurrentRecording,
    downloadCurrentRecording,
    hasRecoverableRecording,
  } = useRecordingController(true)

  const [, navigate] = useLocation()
  useEffect(() => {
    if (hasRecoverableRecording && recorderState === 'idle') {
      navigate('/recordings')
    }
  }, [hasRecoverableRecording, navigate, recorderState])

  const isRecordingInProgress =
    recorderState === 'recording' || recorderState === 'paused'
  const isStarting = recorderState === 'starting'

  const isBusy =
    isRecordingInProgress || recorderState === 'stopping' || isUploading
  useDisablePageRefresh(isBusy)

  const audioInputOptions = useMemo(
    () =>
      audioInputs.map((input, index) => ({
        value: input.deviceId,
        label:
          input.label ||
          t('record:source.fallbackLabel', {
            index: index + 1,
          }),
      })),
    [audioInputs, t]
  )
  const statusLabel = isRecordingInProgress
    ? t(
        isPaused
          ? 'record:status.recordingPaused'
          : 'record:status.recordingInProgress'
      )
    : isStarting
      ? t('record:status.requestingPermission')
      : t('record:status.readyToRecord')

  useEffect(() => {
    const releaseWakeLock = async () => {
      const currentWakeLock = wakeLockRef.current
      if (!currentWakeLock) {
        return
      }
      wakeLockRef.current = null
      await currentWakeLock.release()
    }

    const acquireWakeLock = async () => {
      if (!('wakeLock' in navigator)) {
        return
      }
      try {
        wakeLockRef.current = await navigator.wakeLock.request('screen')
      } catch {
        // Ignore wake lock errors.
      }
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && isRecordingInProgress) {
        void acquireWakeLock()
      }
    }

    if (isRecordingInProgress) {
      void acquireWakeLock()
      document.addEventListener('visibilitychange', handleVisibilityChange)
    } else {
      void releaseWakeLock()
    }

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      void releaseWakeLock()
    }
  }, [isRecordingInProgress])

  const handleStopRequest = () => {
    setUploadAttempts(0)
    setIsStopDialogOpen(true)
  }

  const handleStopAndUpload = async () => {
    const nextAttempt = uploadAttempts + 1
    setUploadAttempts(nextAttempt)

    if (isRecordingInProgress) {
      await stopRecording()
    }

    const file = await uploadCurrentRecording()
    if (file) {
      setIsStopDialogOpen(false)
      navigate(`/recordings/${file.id}`)
      return
    }

    if (nextAttempt >= maxUploadAttempts) {
      const localFile = await downloadCurrentRecording()
      if (localFile) {
        downloadFile(localFile)
        window.alert(
          t('record:alerts.uploadFailedDownloaded', {
            fileName: localFile.name,
          })
        )
      }
      setIsStopDialogOpen(false)
      navigate('/recordings')
    }
  }

  return (
    <>
      <div className="record-component">
        <div className="record-component__content">
          <p
            className={`record-component__status ${
              isPaused
                ? 'record-component__status--paused'
                : isStarting
                  ? 'record-component__status--starting'
                  : ''
            }`}
          >
            <span className="material-icons">
              {isRecordingInProgress
                ? isPaused
                  ? 'pause'
                  : 'fiber_manual_record'
                : isStarting
                  ? 'hourglass_top'
                  : 'mic'}
            </span>
            <span>{statusLabel}</span>
          </p>

          <p className="record-component__timer">
            {formatDuration(recordingDurationMs)}
          </p>

          <SignalLevelMeter
            analyserNode={analyserNode}
            isActive={recorderState === 'recording'}
            ariaLabel={t('record:source.signalLevelAriaLabel')}
          />
          <div className="record-component__source-selector">
            <Select
              label={t('record:source.label')}
              options={audioInputOptions}
              value={selectedAudioInputId}
              clearable={false}
              onChange={(event) =>
                void switchAudioInput(String(event.target.value))
              }
              disabled={
                audioInputOptions.length === 0 || recorderState === 'starting'
              }
            />
            {audioInputOptions.length === 0 && (
              <p className="record-component__source-helper">
                {t('record:source.noInputs')}
              </p>
            )}
          </div>

          {!isRecordingInProgress && (
            <Button
              className="record-component__button"
              onClick={() => void startRecording()}
              disabled={isStarting || isUploading}
              variant="secondary"
              color="error"
              icon={
                <span className="material-icons">
                  {isStarting ? 'hourglass_top' : 'fiber_manual_record'}
                </span>
              }
            >
              {isStarting
                ? t('record:status.requestingPermission')
                : t('record:startRecording')}
            </Button>
          )}

          <div className="record-component__controls">
            {isRecordingInProgress && (
              <>
                <Button
                  color="neutral"
                  variant="secondary"
                  className="record-component__button"
                  onClick={() =>
                    void (isPaused ? resumeRecording() : pauseRecording())
                  }
                  disabled={!canPauseOrStop}
                >
                  <span className="material-icons">
                    {isPaused ? 'play_arrow' : 'pause'}
                  </span>
                  <span>
                    {t(
                      isPaused
                        ? 'record:resumeRecording'
                        : 'record:pauseRecording'
                    )}
                  </span>
                </Button>

                <Button
                  color="error"
                  className="record-component__button"
                  onClick={handleStopRequest}
                  disabled={!canPauseOrStop}
                >
                  <span className="material-icons">stop_circle</span>
                  <span>{t('record:stopRecording')}</span>
                </Button>
              </>
            )}
          </div>
        </div>

        {recordingError && (
          <div className="record-component__error">{recordingError}</div>
        )}
      </div>

      <Modal
        size={ModalSize.MEDIUM}
        isOpen={isStopDialogOpen}
        preventClose={isUploading}
        closeOnEsc={!isUploading}
        closeOnClickOutside={!isUploading}
        onClose={() => {
          if (!isUploading) {
            setIsStopDialogOpen(false)
          }
        }}
        title={t('record:confirmStop.title')}
        rightActions={
          <>
            <Button
              variant="secondary"
              onClick={() => setIsStopDialogOpen(false)}
              disabled={recorderState === 'stopping' || isUploading}
            >
              {t('record:confirmStop.cancel')}
            </Button>
            <Button
              variant="primary"
              onClick={() => void handleStopAndUpload()}
              disabled={recorderState === 'stopping' || isUploading}
            >
              {uploadError
                ? t('record:retryUpload')
                : t('record:confirmStop.confirm')}
            </Button>
          </>
        }
      >
        <p>{t('record:confirmStop.description')}</p>
        {isUploading && (
          <ProgressBar value={uploadProgress} minValue={0} maxValue={100} />
        )}
        {uploadError && (
          <p className="record-component__modal-error">
            {t('record:errors.uploadFailed')}
          </p>
        )}
      </Modal>
    </>
  )
}
