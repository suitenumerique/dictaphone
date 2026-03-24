import { ProgressBar } from '@/components/ProgressBar.tsx'
import { useCreateFile } from '@/features/files/api/createFile.ts'
import { useDisablePageRefresh } from '@/hooks/disablePageRegresh.ts'
import {
  Button,
  Modal,
  ModalSize,
  Tooltip,
} from '@gouvfr-lasuite/cunningham-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useVoiceVisualizer, VoiceVisualizer } from 'react-voice-visualizer'

const extensionByMimeType = {
  'audio/ogg;codecs=opus': 'ogg',
  'audio/webm;codecs=opus': 'webm',
  'audio/mp4': 'mp4',
  'audio/webm': 'webm',
} as const

const preferredMimeType: keyof typeof extensionByMimeType =
  (
    Object.keys(extensionByMimeType) as (keyof typeof extensionByMimeType)[]
  ).find((mimeType) => MediaRecorder.isTypeSupported(mimeType)) ||
  ('audio/webm' as const)

export default function RecordComponent() {
  const { t } = useTranslation(['layout', 'record', 'shared'])
  const createFileMutation = useCreateFile()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadError, setUploadError] = useState(false)
  const wakeLockRef = useRef<WakeLockSentinel | null>(null)

  const recorderControls = useVoiceVisualizer({
    shouldHandleBeforeUnload: false,
    mediaRecorderOptions: {
      mimeType: preferredMimeType,
    },
  })

  const {
    isRecordingInProgress,
    isPausedRecording,
    isProcessingRecordedAudio,
    isProcessingStartRecording,
    duration,
    recordedBlob,
    error,
    formattedRecordingTime,
    startRecording,
    stopRecording,
    togglePauseResume,
    clearCanvas,
    stopAudioPlayback,
    isCleared,
    formattedDuration,
    isPausedRecordedAudio,
  } = recorderControls

  useEffect(() => {
    if (isModalOpen) {
      startRecording()
    }
    // Voice recorder not properly cached
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isModalOpen])

  const isBusy =
    isRecordingInProgress ||
    isProcessingRecordedAudio ||
    isProcessingStartRecording ||
    isUploading
  useDisablePageRefresh(isBusy)

  const recordedFile = useMemo(() => {
    if (!recordedBlob) {
      return null
    }

    const extension = extensionByMimeType[preferredMimeType]
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')

    return new File([recordedBlob], `recording-${timestamp}.${extension}`, {
      type: preferredMimeType,
    })
  }, [recordedBlob])

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

  const resetRecorderState = () => {
    stopAudioPlayback()
    clearCanvas()
    setUploadProgress(0)
    setUploadError(false)
  }

  const closeModal = () => {
    if (isBusy) {
      return
    }
    resetRecorderState()
    setIsModalOpen(false)
  }

  const handleUpload = async () => {
    if (!recordedFile || isBusy) {
      return
    }

    setUploadError(false)
    setUploadProgress(0)
    setIsUploading(true)

    try {
      await createFileMutation.mutateAsync({
        file: recordedFile,
        onProgress: (progress) => setUploadProgress(progress),
      })
      setIsUploading(false)
      resetRecorderState()
      setIsModalOpen(false)
    } catch {
      setUploadError(true)
      setIsUploading(false)
    }
  }

  return (
    <>
      <Tooltip content={t('layout:recordCta')}>
        <Button
          size={'medium'}
          variant="bordered"
          icon={<span className="material-icons">mic</span>}
          onClick={() => setIsModalOpen(true)}
          aria-label={t('layout:recordCta')}
          style={{ borderRadius: '100px' }}
        />
      </Tooltip>

      <Modal
        size={ModalSize.MEDIUM}
        isOpen={isModalOpen}
        onClose={closeModal}
        preventClose={isBusy}
        closeOnEsc={!isBusy}
        closeOnClickOutside={!isBusy}
        title={t('record:title')}
        rightActions={
          <>
            <Button variant="secondary" onClick={closeModal} disabled={isBusy}>
              {t('shared:actions.cancel')}
            </Button>
            <Button onClick={handleUpload} disabled={!recordedFile || isBusy}>
              {t('record:uploadCta')}
            </Button>
          </>
        }
      >
        <div className="record-modal">
          <div className="record-modal__warning">
            <span className="material-icons">warning</span>
            <div>
              <p>{t('record:warnings.stayOnPage')}</p>
              <p>{t('record:warnings.keepPhoneAwake')}</p>
            </div>
          </div>

          <VoiceVisualizer
            controls={recorderControls}
            isControlPanelShown={false}
            isDefaultUIShown={false}
            width={'100%'}
            height={140}
            backgroundColor="black"
          />

          <>
            <div className="voice-visualizer__audio-info-container">
              {isRecordingInProgress && (
                <p className="voice-visualizer__audio-info-time">
                  {formattedRecordingTime}
                </p>
              )}
              {duration && !isProcessingRecordedAudio ? (
                <p>{formattedDuration}</p>
              ) : null}
            </div>

            <div className="voice-visualizer__buttons-container">
              {isRecordingInProgress && (
                <div className="voice-visualizer__btn-container">
                  <button
                    type="button"
                    className={`voice-visualizer__btn-left voice-visualizer__btn--recording ${
                      isPausedRecording
                        ? 'voice-visualizer__btn-left-microphone'
                        : ''
                    }`}
                    onClick={togglePauseResume}
                    aria-label={t(
                      isPausedRecording
                        ? 'record:resumeRecording'
                        : 'record:pauseRecording'
                    )}
                  >
                    {isPausedRecording ? (
                      <span className="material-icons">mic_off</span>
                    ) : (
                      <span className="material-icons">mic</span>
                    )}
                  </button>
                </div>
              )}
              {!isCleared && (
                <button
                  type="button"
                  className={`voice-visualizer__btn-left voice-visualizer__btn--idle ${
                    isRecordingInProgress || isProcessingStartRecording
                      ? 'voice-visualizer__visually-hidden'
                      : ''
                  }`}
                  onClick={togglePauseResume}
                  disabled={isProcessingRecordedAudio}
                  aria-label={t(
                    isPausedRecordedAudio
                      ? 'record:playRecordedAudio'
                      : 'record:pauseRecordedAudio'
                  )}
                >
                  {isProcessingRecordedAudio && (
                    <span className="material-icons">mic</span>
                  )}
                  {isPausedRecordedAudio ? (
                    <span className="material-icons">play_arrow</span>
                  ) : (
                    <span className="material-icons">pause</span>
                  )}
                </button>
              )}
              {isCleared && (
                <button
                  type="button"
                  className={`voice-visualizer__btn-center voice-visualizer__relative voice-visualizer__btn--idle ${
                    isProcessingStartRecording
                      ? 'voice-visualizer__btn-center--border-transparent'
                      : ''
                  }`}
                  onClick={startRecording}
                  disabled={isProcessingStartRecording}
                  aria-label={t('record:startRecording')}
                >
                  {isProcessingStartRecording && (
                    <div className="voice-visualizer__spinner-wrapper">
                      <div className="voice-visualizer__spinner" />
                    </div>
                  )}
                  <span className="material-icons">mic</span>
                </button>
              )}
              <button
                type="button"
                className={`voice-visualizer__btn-center voice-visualizer__btn-center-pause voice-visualizer__btn--recording ${
                  !isRecordingInProgress
                    ? 'voice-visualizer__visually-hidden'
                    : ''
                }`}
                onClick={stopRecording}
                aria-label={t('record:stopRecording')}
              >
                <span className="material-icons">stop</span>
              </button>
            </div>
          </>

          {isUploading && (
            <ProgressBar value={uploadProgress} minValue={0} maxValue={100} />
          )}

          {uploadError && (
            <div className="record-modal__error">
              {t('record:errors.uploadFailed')}
            </div>
          )}

          {error && (
            <div className="record-modal__error">
              {t('record:errors.recordingFailed')}
            </div>
          )}
        </div>
      </Modal>
    </>
  )
}
