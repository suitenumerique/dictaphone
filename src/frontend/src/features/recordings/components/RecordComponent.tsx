import { ProgressBar } from '@/components/ProgressBar.tsx'
import { captureAnalyticsEvent } from '@/features/analytics/hooks/useAnalytics.ts'
import { useCreateFile } from '@/features/files/api/createFile.ts'
import { useDisablePageRefresh } from '@/hooks/disablePageRegresh.ts'
import { Button, Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'wouter'

const extensionByMimeType: Record<string, string> = {
  'audio/ogg;codecs=opus': 'ogg',
  'audio/webm;codecs=opus': 'webm',
  'audio/mp4': 'mp4',
  'audio/webm': 'webm',
}

const preferredMimeType =
  Object.keys(extensionByMimeType).find((mimeType) =>
    MediaRecorder.isTypeSupported(mimeType)
  ) ?? 'audio/webm'

const maxUploadAttempts = 2

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

const getExtensionForMimeType = (mimeType: string) => {
  if (extensionByMimeType[mimeType]) {
    return extensionByMimeType[mimeType]
  }
  if (mimeType.includes('ogg')) {
    return 'ogg'
  }
  if (mimeType.includes('mp4')) {
    return 'mp4'
  }
  return 'webm'
}

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

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error) {
    return error.message
  }
  if (typeof error === 'string') {
    return error
  }
  return undefined
}

type RecorderState =
  | 'idle'
  | 'starting'
  | 'recording'
  | 'paused'
  | 'stopping'
  | 'recorded'
  | 'uploading'
  | 'error'

export default function RecordComponent() {
  const { t } = useTranslation(['layout', 'record', 'shared'])
  const [, navigate] = useLocation()
  const createFileMutation = useCreateFile()
  const [isStopDialogOpen, setIsStopDialogOpen] = useState(false)
  const [recorderState, setRecorderState] = useState<RecorderState>('idle')
  const [recordingDurationMs, setRecordingDurationMs] = useState(0)
  const recordedBlobRef = useRef<Blob | null>(null)
  const [recordedMimeType, setRecordedMimeType] = useState(preferredMimeType)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadError, setUploadError] = useState(false)
  const wakeLockRef = useRef<WakeLockSentinel | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number | null>(null)
  const recordingRealStartDateRef = useRef<Date | null>(null)
  const recordingStartedAtRef = useRef<number | null>(null)
  const accumulatedDurationMsRef = useRef(0)
  const recordingFailedRef = useRef(false)
  const uploadAfterStopRef = useRef(false)
  const uploadAttemptsRef = useRef(0)

  const isRecordingInProgress =
    recorderState === 'recording' || recorderState === 'paused'
  const isPausedRecording = recorderState === 'paused'
  const isStoppingRecording = recorderState === 'stopping'
  const isUploading = recorderState === 'uploading'
  const recordingError = recorderState === 'error'
  const canRetryUpload = recorderState === 'recorded' && uploadError

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const updateDuration = useCallback(() => {
    const startedAt = recordingStartedAtRef.current
    if (startedAt === null) {
      setRecordingDurationMs(accumulatedDurationMsRef.current)
      return
    }
    setRecordingDurationMs(
      accumulatedDurationMsRef.current + (Date.now() - startedAt)
    )
  }, [])

  const startTimer = useCallback(() => {
    stopTimer()
    timerRef.current = window.setInterval(updateDuration, 250)
  }, [stopTimer, updateDuration])

  const cleanupMediaResources = useCallback(() => {
    const recorder = mediaRecorderRef.current
    if (recorder) {
      recorder.ondataavailable = null
      recorder.onstop = null
      recorder.onerror = null
      mediaRecorderRef.current = null
    }

    const stream = mediaStreamRef.current
    if (stream) {
      stream.getTracks().forEach((track) => track.stop())
      mediaStreamRef.current = null
    }
  }, [])

  const resetRecordingState = useCallback(() => {
    stopTimer()
    cleanupMediaResources()
    chunksRef.current = []
    recordingStartedAtRef.current = null
    accumulatedDurationMsRef.current = 0
    setRecorderState('idle')
    setRecordingDurationMs(0)
    recordedBlobRef.current = null
    setRecordedMimeType(preferredMimeType)
    setUploadProgress(0)
    setUploadError(false)
    uploadAttemptsRef.current = 0
  }, [cleanupMediaResources, stopTimer])

  const startRecording = useCallback(async () => {
    if (
      recorderState !== 'idle' &&
      recorderState !== 'recorded' &&
      recorderState !== 'error'
    ) {
      return
    }

    setRecorderState('starting')
    recordingRealStartDateRef.current = new Date()
    recordedBlobRef.current = null
    setRecordedMimeType(preferredMimeType)
    chunksRef.current = []
    recordingFailedRef.current = false
    uploadAfterStopRef.current = false
    uploadAttemptsRef.current = 0
    recordingStartedAtRef.current = null
    accumulatedDurationMsRef.current = 0
    setRecordingDurationMs(0)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream

      const recorder = new MediaRecorder(stream, {
        mimeType: preferredMimeType,
      })
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }

      recorder.onerror = () => {
        recordingFailedRef.current = true
        setRecorderState('error')
        stopTimer()
        cleanupMediaResources()
      }

      recorder.onstop = () => {
        if (recordingFailedRef.current) {
          recordingFailedRef.current = false
          cleanupMediaResources()
          return
        }

        recordedBlobRef.current = new Blob(chunksRef.current, {
          type: recorder.mimeType || preferredMimeType,
        })
        setRecordedMimeType(recorder.mimeType || preferredMimeType)
        stopTimer()
        updateDuration()
        cleanupMediaResources()

        if (uploadAfterStopRef.current) {
          uploadAfterStopRef.current = false
          setRecorderState('uploading')
        } else {
          setRecorderState('recorded')
        }
      }

      recorder.start()
      recordingStartedAtRef.current = Date.now()
      setRecorderState('recording')
      startTimer()
    } catch {
      cleanupMediaResources()
      setRecorderState('error')
    }
  }, [
    cleanupMediaResources,
    recorderState,
    startTimer,
    stopTimer,
    updateDuration,
  ])

  useEffect(() => {
    if (recorderState === 'idle') {
      if (
        new URLSearchParams(window.location.search).get('auto-start') === 'true'
      ) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        startRecording()
        const url = window.location.pathname
        window.history.replaceState({}, document.title, url)
      }
    }
  }, [startRecording, recorderState])

  // Triggered when onstop sets state to 'uploading' after recorder has fully stopped
  useEffect(() => {
    if (recorderState !== 'uploading') return

    const blob = recordedBlobRef.current
    if (!blob) {
      console.error('No recorded blob available, skipping upload')
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRecorderState('error')
      return
    }

    const extension = getExtensionForMimeType(recordedMimeType)
    const recordingCreatedAtDate =
      recordingRealStartDateRef.current ?? new Date()
    const recordingCreatedAt = recordingCreatedAtDate.toISOString()
    const durationSeconds = Math.floor(recordingDurationMs / 1000)
    const recordedFile = new File(
      [blob],
      `${t('record:recordingPrefix')} ${t('shared:utils.formatDateTimeStatic', { value: recordingCreatedAtDate })}.${extension}`,
      { type: recordedMimeType }
    )
    const uploadAttempt = uploadAttemptsRef.current + 1
    uploadAttemptsRef.current = uploadAttempt

    setUploadError(false)
    setUploadProgress(0)

    createFileMutation
      .mutateAsync({
        file: recordedFile,
        createdAt: recordingCreatedAt,
        durationSeconds,
        onProgress: (progress) => setUploadProgress(progress),
      })
      .then((file) => {
        setIsStopDialogOpen(false)
        resetRecordingState()
        navigate(`/recordings/${file.id}`)
      })
      .catch((error: unknown) => {
        if (uploadAttempt < maxUploadAttempts) {
          setUploadError(true)
          setRecorderState('recorded')
          return
        }

        downloadFile(recordedFile)
        captureAnalyticsEvent('recording_upload_failed_downloaded', {
          file_name: recordedFile.name,
          file_size: recordedFile.size,
          file_type: recordedFile.type,
          file_extension: extension,
          file_last_modified: new Date(recordedFile.lastModified).toISOString(),
          recording_created_at: recordingCreatedAt,
          recording_duration_seconds: durationSeconds,
          upload_attempts: uploadAttempt,
          upload_error: getErrorMessage(error),
        })
        resetRecordingState()
        window.alert(
          t('record:alerts.uploadFailedDownloaded', {
            fileName: recordedFile.name,
          })
        )
        navigate('/recordings')
      })
  }, [recorderState]) // eslint-disable-line react-hooks/exhaustive-deps

  const stopRecording = useCallback(
    (andUpload = false) => {
      const recorder = mediaRecorderRef.current
      if (
        !recorder ||
        recorder.state === 'inactive' ||
        (recorderState !== 'recording' && recorderState !== 'paused')
      ) {
        return
      }

      if (recordingStartedAtRef.current !== null) {
        accumulatedDurationMsRef.current +=
          Date.now() - recordingStartedAtRef.current
        recordingStartedAtRef.current = null
      }

      uploadAfterStopRef.current = andUpload
      setRecorderState('stopping')
      stopTimer()
      recorder.stop()
    },
    [recorderState, stopTimer]
  )

  const pauseRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current
    if (!recorder || recorder.state === 'paused') return

    recorder.pause()
    if (recordingStartedAtRef.current !== null) {
      accumulatedDurationMsRef.current +=
        Date.now() - recordingStartedAtRef.current
      recordingStartedAtRef.current = null
    }
    stopTimer()
    updateDuration()
    setRecorderState('paused')
  }, [stopTimer, updateDuration])

  const togglePauseResume = useCallback(() => {
    const recorder = mediaRecorderRef.current
    if (
      !recorder ||
      recorder.state === 'inactive' ||
      isStoppingRecording ||
      (recorderState !== 'recording' && recorderState !== 'paused')
    ) {
      return
    }

    if (recorder.state === 'recording') {
      pauseRecording()
      return
    }

    if (recorder.state === 'paused') {
      recorder.resume()
      recordingStartedAtRef.current = Date.now()
      startTimer()
      setRecorderState('recording')
    }
  }, [isStoppingRecording, pauseRecording, recorderState, startTimer])

  useEffect(
    () => () => {
      stopTimer()
      cleanupMediaResources()
    },
    [cleanupMediaResources, stopTimer]
  )

  const isBusy =
    recorderState === 'starting' ||
    recorderState === 'recording' ||
    recorderState === 'paused' ||
    recorderState === 'stopping' ||
    recorderState === 'uploading'
  useDisablePageRefresh(isBusy)

  useEffect(() => {
    const releaseWakeLock = async () => {
      const currentWakeLock = wakeLockRef.current
      if (currentWakeLock) {
        wakeLockRef.current = null
        await currentWakeLock.release()
      }
    }

    const acquireWakeLock = async () => {
      if (!('wakeLock' in navigator)) {
        return
      }
      try {
        wakeLockRef.current = await navigator.wakeLock.request('screen')
      } catch {
        // Ignore wake lock errors and keep recording available anyway.
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
    if (recorderState !== 'recording' && recorderState !== 'paused') {
      return
    }
    setIsStopDialogOpen(true)
  }

  const confirmStopRecording = () => {
    stopRecording(true)
    setIsStopDialogOpen(false)
  }

  const retryUpload = () => {
    if (
      recorderState !== 'recorded' ||
      !recordedBlobRef.current ||
      uploadAttemptsRef.current >= maxUploadAttempts
    ) {
      return
    }

    setRecorderState('uploading')
  }

  return (
    <>
      <div className="record-component">
        <div
          className={`record-component__content ${
            canRetryUpload ? 'record-component__content--recovery' : ''
          }`}
        >
          <p
            className={`record-component__status ${
              isPausedRecording ? 'record-component__status--paused' : ''
            } ${canRetryUpload ? 'record-component__status--error' : ''}`}
          >
            <span className="material-icons">
              {canRetryUpload
                ? 'cloud_off'
                : isPausedRecording
                  ? 'pause'
                  : 'fiber_manual_record'}
            </span>
            <span>
              {canRetryUpload
                ? t('record:status.uploadFailed')
                : t(
                    isPausedRecording
                      ? 'record:status.recordingPaused'
                      : 'record:status.recordingInProgress'
                  )}
            </span>
          </p>

          <p className="record-component__timer">
            {formatDuration(recordingDurationMs)}
          </p>

          {canRetryUpload && (
            <div className="record-component__recovery" role="alert">
              <div className="record-component__recovery-icon">
                <span className="material-icons">priority_high</span>
              </div>
              <div className="record-component__recovery-content">
                <p className="record-component__recovery-title">
                  {t('record:uploadRecovery.title')}
                </p>
                <p className="record-component__recovery-description">
                  {t('record:uploadRecovery.description')}
                </p>
              </div>
            </div>
          )}

          <div
            className={`record-component__controls ${
              canRetryUpload ? 'record-component__controls--single' : ''
            }`}
          >
            {canRetryUpload ? (
              <Button
                className="record-component__button record-component__retry-button"
                onClick={retryUpload}
                aria-label={t('record:retryUpload')}
              >
                <span className="material-icons">refresh</span>
                <span>{t('record:retryUpload')}</span>
              </Button>
            ) : (
              <>
                <Button
                  color="neutral"
                  variant="secondary"
                  className="record-component__button"
                  onClick={togglePauseResume}
                  disabled={!isRecordingInProgress || isStoppingRecording}
                  aria-label={t(
                    isPausedRecording
                      ? 'record:resumeRecording'
                      : 'record:pauseRecording'
                  )}
                >
                  <span className="material-icons">
                    {isPausedRecording ? 'play_arrow' : 'pause'}
                  </span>
                  <span>
                    {t(
                      isPausedRecording
                        ? 'record:resumeRecording'
                        : 'record:pauseRecording'
                    )}
                  </span>
                </Button>

                <Button
                  className={`record-component__button`}
                  color="error"
                  onClick={handleStopRequest}
                  disabled={!isRecordingInProgress || isStoppingRecording}
                  aria-label={t('record:stopRecording')}
                >
                  <span className="material-icons">stop_circle</span>
                  <span>{t('record:stopRecording')}</span>
                </Button>
              </>
            )}
          </div>
        </div>

        {isUploading && (
          <ProgressBar value={uploadProgress} minValue={0} maxValue={100} />
        )}

        {uploadError && !canRetryUpload && (
          <div className="record-component__error">
            {t('record:errors.uploadFailed')}
          </div>
        )}

        {recordingError && (
          <div className="record-component__error">
            {t('record:errors.recordingFailed')}
          </div>
        )}
      </div>

      <Modal
        size={ModalSize.MEDIUM}
        isOpen={isStopDialogOpen}
        onClose={() => setIsStopDialogOpen(false)}
        title={t('record:confirmStop.title')}
        rightActions={
          <>
            <Button
              variant="secondary"
              onClick={() => setIsStopDialogOpen(false)}
              disabled={isStoppingRecording}
            >
              {t('record:confirmStop.cancel')}
            </Button>
            <Button
              variant="primary"
              onClick={confirmStopRecording}
              disabled={isStoppingRecording}
            >
              {t('record:confirmStop.confirm')}
            </Button>
          </>
        }
      >
        <p>{t('record:confirmStop.description')}</p>
      </Modal>
    </>
  )
}
