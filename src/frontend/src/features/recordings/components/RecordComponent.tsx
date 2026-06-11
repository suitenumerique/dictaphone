import { SignalLevelMeter } from '@/features/recordings/components/SignalLevelMeter.tsx'
import { useRecordingController } from '@/features/recordings/hooks/useRecordingController.ts'
import { useDisablePageRefresh } from '@/hooks/disablePageRegresh.ts'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'wouter'
import clsx from 'clsx'
import { DropdownMenu, DropdownMenuOption } from '@gouvfr-lasuite/ui-kit'
import { ChevronDown } from '@gouvfr-lasuite/ui-kit/icons'

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

export default function RecordComponent() {
  const { t } = useTranslation(['record'])
  const wakeLockRef = useRef<WakeLockSentinel | null>(null)
  const stopInFlightRef = useRef(false)

  const {
    recorderState,
    selectedAudioInputId,
    audioInputs,
    recordingDurationMs,
    analyserNode,
    recordingError,
    isPaused,
    canPauseOrStop,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopAndDispose,
    switchAudioInput,
  } = useRecordingController(true)

  const [, navigate] = useLocation()
  const isRecordingInProgress =
    recorderState === 'recording' || recorderState === 'paused'
  const isStarting = recorderState === 'starting'
  const isStopping = recorderState === 'stopping'

  const isBusy = isStarting || isRecordingInProgress || isStopping
  useDisablePageRefresh(isBusy, t('record:preventGoBackAlert'))

  const [openInputSelection, setOpenInputSelection] = useState(false)
  const audioInputOptions = useMemo<DropdownMenuOption[]>(
    () =>
      audioInputs.map(
        (input, index) =>
          ({
            value: input.deviceId,
            isChecked: input.deviceId === selectedAudioInputId,
            callback: () => switchAudioInput(input.deviceId),
            label:
              input.label ||
              t('record:source.fallbackLabel', {
                index: index + 1,
              }),
          }) satisfies DropdownMenuOption
      ),
    [audioInputs, selectedAudioInputId, switchAudioInput, t]
  )
  const selectedSourceLabel = useMemo(
    () => audioInputOptions.find((option) => option.isChecked)?.label,
    [audioInputOptions]
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

  const handleStop = useCallback(async () => {
    if (stopInFlightRef.current || !isRecordingInProgress) {
      return
    }

    stopInFlightRef.current = true
    try {
      await stopAndDispose()
      navigate('/recordings')
    } finally {
      stopInFlightRef.current = false
    }
  }, [isRecordingInProgress, navigate, stopAndDispose])

  return (
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
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <span className="material-icons" aria-hidden="true">
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

        <div className="record-component__signal-timer-container">
          <SignalLevelMeter
            analyserNode={analyserNode}
            isActive={recorderState === 'recording'}
            ariaLabel={t('record:source.signalLevelAriaLabel')}
            noSoundDetectedLabel={t('record:source.noSoundDetected')}
            lowSoundLabel={t('record:source.lowSound')}
            soundOkLabel={t('record:source.soundOk')}
          />
          <p
            className={clsx(
              'record-component__timer',
              recorderState === 'paused' ? 'paused' : ''
            )}
          >
            {formatDuration(recordingDurationMs)}
          </p>
        </div>
        <div className="record-component__footer">
          <DropdownMenu
            topMessage={t('record:source.ariaLabel')}
            options={audioInputOptions}
            isOpen={openInputSelection}
            onOpenChange={setOpenInputSelection}
          />
          <Button
            color="neutral"
            variant="tertiary"
            size={'nano'}
            disabled={audioInputOptions.length === 0}
            onClick={() => setOpenInputSelection(!openInputSelection)}
            aria-label={t('record:source.ariaLabel')}
          >
            <span className="source-btn">
              {selectedSourceLabel ?? t('record:source.noInputs')}
            </span>
            <ChevronDown size="small" />
          </Button>

          {!isRecordingInProgress && (
            <Button
              className="record-component__button"
              onClick={() => void startRecording()}
              disabled={isStarting || isStopping}
              variant="secondary"
              color="error"
              icon={
                <span className="material-icons" aria-hidden="true">
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
                  <span className="material-icons" aria-hidden="true">
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
                  onClick={() => void handleStop()}
                  disabled={!canPauseOrStop}
                >
                  <span className="material-icons" aria-hidden="true">
                    stop_circle
                  </span>
                  <span>{t('record:stopRecording')}</span>
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      {recordingError && (
        <div className="record-component__error" role="alert">
          {recordingError}
        </div>
      )}
    </div>
  )
}
