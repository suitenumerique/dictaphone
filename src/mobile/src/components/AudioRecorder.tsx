import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  Button,
  Linking,
  Pressable,
  StyleSheet,
  View,
} from 'react-native'
import { useTranslation } from 'react-i18next'
import { Lucide } from '@react-native-vector-icons/lucide'
import {
  type PermissionResponse,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioPlayer,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio'
import { trigger as triggerHaptic } from 'react-native-haptic-feedback'
import { formatDuration } from '@/features/recordings/utils/formatDuration'
import { useNavigation, usePreventRemove } from '@react-navigation/core'
import uuid from 'react-native-uuid'
import { useLocalRecordings } from '@/features/recordings/hooks/useLocalRecordings'
import { deleteLocalRecordingFile } from '@/utils/deleteLocalRecordingFile'
import { AppText } from './AppText'
import { colors } from './colors'
import { useResetNavigationHistory } from '@/navigation/useRestNavigationHistory' // @ts-expect-error SVG
import PauseIcon from '@/assets/icons/pause-recording.svg' // @ts-expect-error SVG
import StopIcon from '@/assets/icons/stop-recording.svg' // @ts-expect-error SVG
import PlayIcon from '@/assets/icons/resume-recording.svg'
import { useConfigStore } from '@/services/configStore'
import { useSettingsStore } from '@/services/storage'

const HEAVY_HAPTIC_INTERVAL_MS = 900
const HAPTIC_OPTIONS = {
  enableVibrateFallback: true,
  ignoreAndroidSystemSettings: false,
}

type RecorderPhase =
  | 'idle'
  | 'starting'
  | 'recording'
  | 'pausing'
  | 'paused'
  | 'resuming'
  | 'stopping'

const RECORDING_PHASES = new Set<RecorderPhase>([
  'recording',
  'pausing',
  'paused',
  'resuming',
  'stopping',
])
const LOADING_PHASES = new Set<RecorderPhase>([
  'starting',
  'pausing',
  'resuming',
  'stopping',
])
const PAUSED_PHASES = new Set<RecorderPhase>(['paused', 'resuming'])
const STOPPABLE_PHASES = new Set<RecorderPhase>(['recording', 'paused'])
const DURATION_POLLING_PHASES = new Set<RecorderPhase>(['recording', 'pausing'])

let recorderActionQueue: Promise<void> = Promise.resolve()

const enqueueRecorderAction = <Result,>(
  action: () => Promise<Result>
): Promise<Result> => {
  const queuedAction = recorderActionQueue.then(action, action)
  recorderActionQueue = queuedAction.then(
    () => undefined,
    () => undefined
  )
  return queuedAction
}

const waitForNextFrame = () =>
  new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      resolve()
    })
  })

const wait = async (
  durationMs: number,
  shouldContinue: () => boolean = () => true
) => {
  const endTime = Date.now() + durationMs

  while (shouldContinue()) {
    const remainingMs = endTime - Date.now()
    if (remainingMs <= 0) {
      return
    }

    await new Promise<void>((resolve) => {
      setTimeout(resolve, Math.min(remainingMs, 50))
    })
  }
}

export const AudioRecorder = () => {
  const { t } = useTranslation()
  const audioRecorder = useAudioRecorder({
    ...RecordingPresets.HIGH_QUALITY,
    directory: 'document',
  })
  const recorderState = useAudioRecorderState(audioRecorder, 200)
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const startCuePlayer = useAudioPlayer(require('../assets/sounds/start.wav'))
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const endCuePlayer = useAudioPlayer(require('../assets/sounds/end.wav'))
  const maxDurationSeconds = useConfigStore(
    // We add a buffer to avoid the recording from being rejected due to timing issues
    (state) => Math.max(state.maxDurationSeconds - 60, 0)
  )
  const newTranscriptionLanguage = useSettingsStore(
    (state) => state.newTranscriptionLanguage
  )
  const appLanguage = useSettingsStore((state) => state.settings.language)
  const selectedTranscriptionLanguage = useMemo(
    () => newTranscriptionLanguage ?? (appLanguage === 'en' ? 'en' : 'fr'),
    [appLanguage, newTranscriptionLanguage]
  )
  const [recorderPhase, setRecorderPhase] = useState<RecorderPhase>('idle')
  const [shouldResetNavigation, setShouldResetNavigation] = useState(false)
  const [recordingTimeMs, setRecordingTimeMs] = useState(0)
  const [permissionStatus, setPermissionStatus] =
    useState<PermissionResponse['status']>('undetermined' as const)
  const { addRecording } = useLocalRecordings()
  const resetNavigationHistory = useResetNavigationHistory()
  const navigation = useNavigation()
  const recordingStartDateTime = useRef<Date | null>(null)
  const isMountedRef = useRef(true)
  const recorderPhaseRef = useRef<RecorderPhase>('idle')
  const lifecycleTokenRef = useRef(0)
  const autoStopHapticsInterval = useRef<ReturnType<typeof setInterval> | null>(
    null
  )
  const hasReachedMaxDuration = useRef(false)
  const hasAutoStartedRef = useRef(false)

  const isRecording = RECORDING_PHASES.has(recorderPhase)
  const isPaused = PAUSED_PHASES.has(recorderPhase)
  const isLoading = LOADING_PHASES.has(recorderPhase)
  const isStopping = recorderPhase === 'stopping'
  const shouldPollRecordingDuration = DURATION_POLLING_PHASES.has(recorderPhase)

  const recordTimeLabel = useMemo(
    () => formatDuration(recordingTimeMs),
    [recordingTimeMs]
  )

  const stopAutoStopHaptics = useCallback(() => {
    if (autoStopHapticsInterval.current) {
      clearInterval(autoStopHapticsInterval.current)
      autoStopHapticsInterval.current = null
    }
  }, [])

  const setRecorderPhaseState = useCallback((nextPhase: RecorderPhase) => {
    recorderPhaseRef.current = nextPhase
    if (!isMountedRef.current) {
      return
    }
    setRecorderPhase(nextPhase)
  }, [])

  const invalidateLifecycle = useCallback(() => {
    lifecycleTokenRef.current += 1
  }, [])

  const beginLifecycleAction = useCallback(
    (nextPhase: RecorderPhase) => {
      lifecycleTokenRef.current += 1
      setRecorderPhaseState(nextPhase)
      return lifecycleTokenRef.current
    },
    [setRecorderPhaseState]
  )

  const isCurrentLifecycle = useCallback(
    (lifecycleToken: number) =>
      isMountedRef.current && lifecycleTokenRef.current === lifecycleToken,
    []
  )

  const setRecorderPhaseIfCurrent = useCallback(
    (lifecycleToken: number, nextPhase: RecorderPhase) => {
      if (!isCurrentLifecycle(lifecycleToken)) {
        return false
      }

      setRecorderPhaseState(nextPhase)
      return true
    },
    [isCurrentLifecycle, setRecorderPhaseState]
  )

  const playCueSound = useCallback(
    async (
      cuePlayer: ReturnType<typeof useAudioPlayer>,
      waitUntilFinished: boolean = false,
      shouldContinue: () => boolean = () => true
    ) => {
      try {
        await cuePlayer.seekTo(0)
        if (!shouldContinue()) {
          return
        }

        cuePlayer.play()
        if (!shouldContinue()) {
          return
        }

        if (waitUntilFinished) {
          const cueDurationMs = Math.max(Math.ceil(cuePlayer.duration * 1000), 250)
          await wait(cueDurationMs, shouldContinue)
        }
      } catch (error) {
        console.error('Failed to play cue sound:', error)
      }
    },
    []
  )

  const deactivateAudioSession = useCallback(async () => {
    try {
      await setAudioModeAsync({ allowsRecording: false })
    } catch (error) {
      console.error('Failed to deactivate the audio session:', error)
    }
  }, [])

  const stopRecorderIfNeeded = useCallback(
    async (options?: { force?: boolean; updateState?: boolean }) => {
      const force = options?.force ?? false
      const updateState = options?.updateState ?? true
      if (!force && !RECORDING_PHASES.has(recorderPhaseRef.current)) {
        return null
      }

      try {
        await audioRecorder.stop()
        return {
          uri: audioRecorder.uri ?? recorderState.url,
          durationSeconds: recorderState.durationMillis / 1000,
        }
      } catch (error) {
        console.error('Failed to stop recorder while clearing state:', error)
        return null
      } finally {
        if (updateState) {
          setRecorderPhaseState('idle')
        } else {
          recorderPhaseRef.current = 'idle'
        }
      }
    },
    [audioRecorder, recorderState.durationMillis, recorderState.url, setRecorderPhaseState]
  )

  const showMaxDurationAlert = useCallback(() => {
    stopAutoStopHaptics()
    triggerHaptic('impactHeavy', HAPTIC_OPTIONS)
    autoStopHapticsInterval.current = setInterval(() => {
      triggerHaptic('impactHeavy', HAPTIC_OPTIONS)
    }, HEAVY_HAPTIC_INTERVAL_MS)

    Alert.alert(
      t('home.recordingMaxDurationTitle'),
      t('home.recordingMaxDurationMessage'),
      [
        {
          text: t('home.recordingMaxDurationConfirm'),
          onPress: stopAutoStopHaptics,
        },
      ],
      {
        cancelable: false,
        onDismiss: stopAutoStopHaptics,
      }
    )
  }, [stopAutoStopHaptics, t])

  const clearRecording = useCallback(
    async (options?: { updateState?: boolean; clearFile?: boolean }) => {
      const updateState = options?.updateState ?? true
      invalidateLifecycle()

      await enqueueRecorderAction(async () => {
        const stoppedRecording = await stopRecorderIfNeeded({
          force: true,
          updateState,
        })
        stopAutoStopHaptics()
        hasReachedMaxDuration.current = false
        recordingStartDateTime.current = null
        if (updateState && isMountedRef.current) {
          setRecordingTimeMs(0)
        }
        const localRecordingPath = stoppedRecording?.uri ?? null
        if (options?.clearFile && localRecordingPath) {
          try {
            await deleteLocalRecordingFile(localRecordingPath)
          } catch (error) {
            console.error('Failed to delete local discarded recording:', error)
          }
        }
        await deactivateAudioSession()
      })
    },
    [deactivateAudioSession, invalidateLifecycle, stopAutoStopHaptics, stopRecorderIfNeeded]
  )

  useEffect(() => {
    isMountedRef.current = true
    requestRecordingPermissionsAsync()
      .then(({ status }) => {
        if (!isMountedRef.current) {
          return
        }
        setPermissionStatus(status)
      })
      .catch((error) => {
        console.error('Failed to request recording permissions:', error)
      })

    return () => {
      isMountedRef.current = false
      stopAutoStopHaptics()
      void clearRecording({ updateState: false })
    }
  }, [clearRecording, stopAutoStopHaptics])

  usePreventRemove(isRecording, ({ data }) => {
    Alert.alert(
      t('home.discardRecordingTitle'),
      t('home.discardRecordingMessage'),
      [
        {
          text: t('home.discardRecordingCancel'),
          style: 'cancel',
          onPress: () => {},
        },
        {
          text: t('home.discardRecordingConfirm'),
          style: 'destructive',
          onPress: () => {
            void (async () => {
              await clearRecording({ clearFile: true })
              setRecorderPhaseState('idle')
              setRecordingTimeMs(0)
              navigation.dispatch(data.action)
              // And we reset the navigation history to the main screen too
              resetNavigationHistory('Main')
            })()
          },
        },
      ]
    )
  })

  useEffect(() => {
    if (!shouldResetNavigation || isRecording) {
      return
    }

    setShouldResetNavigation(false)
    resetNavigationHistory('Main')
  }, [isRecording, resetNavigationHistory, shouldResetNavigation])

  useEffect(() => {
    if (!shouldPollRecordingDuration) {
      return
    }
    setRecordingTimeMs(recorderState.durationMillis)
  }, [recorderState.durationMillis, shouldPollRecordingDuration])

  const handleStartRecording = useCallback(async () => {
    if (recorderPhaseRef.current !== 'idle') {
      return
    }

    const lifecycleToken = beginLifecycleAction('starting')

    await enqueueRecorderAction(async () => {
      if (!isCurrentLifecycle(lifecycleToken)) {
        return
      }

      try {
        const permissionsResponse = await requestRecordingPermissionsAsync()
        if (!isCurrentLifecycle(lifecycleToken)) {
          return
        }
        setPermissionStatus(permissionsResponse.status)

        if (!permissionsResponse.granted) {
          console.warn('Permissions are not granted')
          setRecorderPhaseIfCurrent(lifecycleToken, 'idle')
          return
        }

        await setAudioModeAsync({
          playsInSilentMode: true,
          allowsRecording: true,
          allowsBackgroundRecording: true,
        })
        await playCueSound(startCuePlayer, true, () =>
          isCurrentLifecycle(lifecycleToken)
        )
        if (!isCurrentLifecycle(lifecycleToken)) {
          return
        }

        await audioRecorder.prepareToRecordAsync({
          ...RecordingPresets.HIGH_QUALITY,
          directory: 'document',
        })
        audioRecorder.record()

        hasReachedMaxDuration.current = false
        recordingStartDateTime.current = new Date()

        if (isCurrentLifecycle(lifecycleToken)) {
          setRecordingTimeMs(0)
          setRecorderPhaseState('recording')
        } else {
          await stopRecorderIfNeeded({ force: true, updateState: false })
          await deactivateAudioSession()
        }
      } catch (error) {
        console.error('Failed to start recording:', error)
        setRecorderPhaseIfCurrent(lifecycleToken, 'idle')
      }
    })
  }, [
    audioRecorder,
    beginLifecycleAction,
    deactivateAudioSession,
    isCurrentLifecycle,
    playCueSound,
    setRecorderPhaseIfCurrent,
    setRecorderPhaseState,
    startCuePlayer,
    stopRecorderIfNeeded,
  ])

  useEffect(() => {
    if (permissionStatus === 'granted' && !hasAutoStartedRef.current) {
      hasAutoStartedRef.current = true
      void handleStartRecording()
    }
  }, [permissionStatus, handleStartRecording])

  const onPauseRecord = useCallback(async () => {
    if (recorderPhaseRef.current !== 'recording') {
      return
    }

    const lifecycleToken = beginLifecycleAction('pausing')

    await enqueueRecorderAction(async () => {
      if (!isCurrentLifecycle(lifecycleToken)) {
        return
      }

      try {
        audioRecorder.pause()
        await playCueSound(endCuePlayer, true, () =>
          isCurrentLifecycle(lifecycleToken)
        )
        setRecorderPhaseIfCurrent(lifecycleToken, 'paused')
      } catch (error) {
        console.error('Failed to pause recording:', error)
        setRecorderPhaseIfCurrent(lifecycleToken, 'recording')
      }
    })
  }, [
    audioRecorder,
    beginLifecycleAction,
    endCuePlayer,
    isCurrentLifecycle,
    playCueSound,
    setRecorderPhaseIfCurrent,
  ])

  const onResumeRecord = useCallback(async () => {
    if (recorderPhaseRef.current !== 'paused') {
      return
    }

    const lifecycleToken = beginLifecycleAction('resuming')

    await enqueueRecorderAction(async () => {
      if (!isCurrentLifecycle(lifecycleToken)) {
        return
      }

      try {
        await playCueSound(startCuePlayer, true, () =>
          isCurrentLifecycle(lifecycleToken)
        )
        if (!isCurrentLifecycle(lifecycleToken)) {
          return
        }

        audioRecorder.record()
        setRecorderPhaseIfCurrent(lifecycleToken, 'recording')
      } catch (error) {
        console.error('Failed to resume recording:', error)
        setRecorderPhaseIfCurrent(lifecycleToken, 'paused')
      }
    })
  }, [
    audioRecorder,
    beginLifecycleAction,
    isCurrentLifecycle,
    playCueSound,
    setRecorderPhaseIfCurrent,
    startCuePlayer,
  ])

  const onStopRecord = useCallback(async () => {
    const previousPhase = recorderPhaseRef.current
    if (!STOPPABLE_PHASES.has(previousPhase)) {
      return false
    }

    const wasPaused = previousPhase === 'paused'
    const lifecycleToken = beginLifecycleAction('stopping')

    return enqueueRecorderAction(async () => {
      if (!isCurrentLifecycle(lifecycleToken)) {
        return false
      }

      try {
        await waitForNextFrame()
        if (!isCurrentLifecycle(lifecycleToken)) {
          return false
        }

        await audioRecorder.stop()
        const localRecordingPath = audioRecorder.uri ?? recorderState.url
        if (!localRecordingPath) {
          setRecorderPhaseIfCurrent(lifecycleToken, previousPhase)
          return false
        }

        if (!wasPaused) {
          await playCueSound(endCuePlayer, true, () =>
            isCurrentLifecycle(lifecycleToken)
          )
        }
        if (!isCurrentLifecycle(lifecycleToken)) {
          return false
        }

        await deactivateAudioSession()
        if (!isCurrentLifecycle(lifecycleToken)) {
          return false
        }

        const startedAt = recordingStartDateTime.current ?? new Date()

        const title = `${t('home.recordingPrefix')} ${t(
          'shared.utils.formatDateTimeStatic',
          { value: startedAt }
        )}`
        addRecording({
          created_at: startedAt.toISOString(),
          duration_seconds: recorderState.durationMillis / 1000,
          filePath: localRecordingPath,
          title,
          id: uuid.v4(),
          language: selectedTranscriptionLanguage,
          uploadingStatus: 'to_upload',
        })

        recordingStartDateTime.current = null
        hasReachedMaxDuration.current = false
        setRecordingTimeMs(0)
        setRecorderPhaseState('idle')
        setShouldResetNavigation(true)
        return true
      } catch (error) {
        console.error('Failed to stop recording:', error)
        setRecorderPhaseIfCurrent(lifecycleToken, previousPhase)
        return false
      }
    })
  }, [
    addRecording,
    audioRecorder,
    beginLifecycleAction,
    deactivateAudioSession,
    endCuePlayer,
    isCurrentLifecycle,
    playCueSound,
    recorderState.durationMillis,
    recorderState.url,
    setRecorderPhaseIfCurrent,
    setRecorderPhaseState,
    selectedTranscriptionLanguage,
    t,
  ])

  useEffect(() => {
    if (
      !isRecording ||
      isPaused ||
      isStopping ||
      hasReachedMaxDuration.current ||
      recordingTimeMs < maxDurationSeconds * 1000
    ) {
      return
    }

    hasReachedMaxDuration.current = true

    onStopRecord()
      .then((didStop) => {
        if (didStop && isMountedRef.current) {
          showMaxDurationAlert()
        }
      })
      .catch((error) => {
        console.error('Failed to stop recording at max duration:', error)
      })
  }, [
    isPaused,
    isRecording,
    isStopping,
    maxDurationSeconds,
    onStopRecord,
    recordingTimeMs,
    showMaxDurationAlert,
  ])

  useEffect(() => {
    if (permissionStatus === 'denied') {
      Alert.alert(t('home.permissionDenied'), t('home.recordingDisabled'), [
        {
          text: t('home.permissionCancel'),
          onPress: () => {
            resetNavigationHistory('Main')
          },
        },
        {
          text: t('home.openSettings'),
          onPress: () => {
            Linking.openSettings()
          },
        },
      ])
    }
  }, [resetNavigationHistory, permissionStatus, t])

  if (permissionStatus === 'denied') {
    return (
      <View style={styles.activeContainer}>
        <View style={styles.statusSection}>
          <View style={styles.statusBadge}>
            <Lucide name="mic-off" size={18} color={colors.errorSecondary} />
          </View>
          <AppText variant="body" align="center">
            {t('home.recordingDisabled')}
          </AppText>
          <Button
            onPress={() => Linking.openSettings()}
            title={t('home.openSettings')}
          />
        </View>
      </View>
    )
  }

  return (
    <View style={styles.activeContainer}>
      <View style={styles.statusSection}>
        <View style={styles.statusBadge}>
          {isPaused ? (
            <Lucide
              name="pause-circle"
              size={18}
              color={colors.neutralTertiary}
            />
          ) : (
            <Lucide
              name="audio-lines"
              size={18}
              color={colors.errorSecondary}
            />
          )}
          <AppText
            variant="bodyMedium"
            style={[styles.statusTitle, isPaused && styles.statusTitlePaused]}
          >
            {t(isPaused ? 'home.recordingPaused' : 'home.recordingInProgress')}
          </AppText>
        </View>

        <AppText
          variant="muted"
          size="md"
          align="center"
          style={styles.statusSubtitle}
        >
          {t(
            isPaused ? 'home.recordingSubtitlePaused' : 'home.recordingSubtitle'
          )}
        </AppText>
      </View>

      <View style={styles.timerSection}>
        {isStopping ? (
          <ActivityIndicator size="large" color={colors.errorSecondary} />
        ) : (
          <AppText style={[styles.timer, isPaused && styles.timerPaused]}>
            {recordTimeLabel}
          </AppText>
        )}
      </View>

      <View style={styles.controlsRow}>
        <Pressable
          style={({ pressed }) => [
            styles.controlButton,
            styles.pauseButton,
            isLoading && styles.buttonDisabled,
            pressed && styles.pauseButtonPressed,
          ]}
          onPress={() => {
            void (isPaused ? onResumeRecord() : onPauseRecord())
          }}
          disabled={isLoading}
        >
          {isPaused ? <PlayIcon /> : <PauseIcon />}
          <AppText variant="button" color={colors.neutralSecondary}>
            {isPaused ? t('home.resume') : t('home.pause')}
          </AppText>
        </Pressable>

        <Pressable
          style={({ pressed }) => [
            styles.controlButton,
            styles.endButton,
            isLoading && styles.buttonDisabled,
            pressed && styles.endButtonPressed,
          ]}
          onPress={() => {
            void onStopRecord()
          }}
          disabled={isLoading}
        >
          <StopIcon />
          <AppText variant="button">{t('home.end')}</AppText>
        </Pressable>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  activeContainer: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: 30,
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 36,
    paddingBottom: 20,
  },
  statusSection: {
    alignItems: 'center',
    gap: 12,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  statusTitle: {
    marginBottom: 3,
    color: colors.errorSecondary,
  },
  statusTitlePaused: {
    color: colors.neutralTertiary,
  },
  statusSubtitle: {
    maxWidth: 320,
    lineHeight: 22,
  },
  timerSection: {
    width: '100%',
    justifyContent: 'center',
    alignItems: 'center',
  },
  timer: {
    fontSize: 44,
    lineHeight: 80,
    fontWeight: '800',
    fontVariant: ['tabular-nums'],
  },
  timerPaused: {
    color: colors.neutralSecondary,
  },
  controlsRow: {
    flexDirection: 'row',
    width: '100%',
    justifyContent: 'center',
    gap: 14,
  },
  controlButton: {
    flex: 1,
    minHeight: 46,
    borderRadius: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  pauseButton: {
    backgroundColor: colors.backgroundNeutralSecondary,
  },
  pauseButtonPressed: {
    backgroundColor: colors.backgroundNeutralSecondaryPressed,
  },
  endButton: {
    backgroundColor: colors.backgroundError,
  },
  endButtonPressed: {
    backgroundColor: colors.backgroundErrorPressed,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
})
