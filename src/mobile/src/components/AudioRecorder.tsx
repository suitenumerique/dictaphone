import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  Button,
  Linking,
  NativeModules,
  Platform,
  Pressable,
  StyleSheet,
  View,
} from 'react-native'
import { useTranslation } from 'react-i18next'
import { Lucide } from '@react-native-vector-icons/lucide'
import {
  AudioBuffer,
  AudioContext,
  AudioManager,
  AudioRecorder as AudioRecorderApi,
  FileDirectory,
  FileFormat,
  FilePreset,
} from 'react-native-audio-api'
import { trigger as triggerHaptic } from 'react-native-haptic-feedback'
import { formatDuration } from '@/features/recordings/utils/formatDuration'
import { useNavigation, usePreventRemove } from '@react-navigation/core'
import { PermissionStatus } from 'react-native-audio-api/lib/typescript/system/types'
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

AudioManager.setAudioSessionOptions({
  iosCategory: 'playAndRecord',
  iosMode: 'default',
  iosOptions: ['defaultToSpeaker'],
})

const audioRecorder = new AudioRecorderApi()
const audioContext = new AudioContext()
const startSound = 'start.wav'
const endSound = 'end.wav'
const { BundlePath } = NativeModules as {
  BundlePath?: {
    getBundlePath: () => Promise<string>
  }
}
let iosBundlePathPromise: Promise<string | null> | null = null

const cueSoundAssets = {
  start: startSound,
  end: endSound,
} as const
const cueSoundBuffers: Record<keyof typeof cueSoundAssets, AudioBuffer | null> =
  {
    start: null,
    end: null,
  }
const cueSoundBufferPromises: Record<
  keyof typeof cueSoundAssets,
  Promise<AudioBuffer> | null
> = {
  start: null,
  end: null,
}

const HEAVY_HAPTIC_INTERVAL_MS = 900
const HAPTIC_OPTIONS = {
  enableVibrateFallback: true,
  ignoreAndroidSystemSettings: false,
}
const isAndroid = Platform.OS === 'android'
const noopNotificationSubscription = { remove: () => {} }

type RecordingNotificationManagerType =
  typeof import('react-native-audio-api').RecordingNotificationManager
let recordingNotificationManager: RecordingNotificationManagerType | null = null

const getRecordingNotificationManager =
  (): RecordingNotificationManagerType | null => {
    if (!isAndroid) {
      return null
    }

    if (!recordingNotificationManager) {
      recordingNotificationManager =
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        require('react-native-audio-api').RecordingNotificationManager
    }

    return recordingNotificationManager
  }

const showRecordingNotificationSafely = async (
  ...args: Parameters<RecordingNotificationManagerType['show']>
) => {
  const manager = getRecordingNotificationManager()
  if (!manager) {
    return
  }

  await manager.show(...args)
}

const hideRecordingNotificationSafely = () => {
  const manager = getRecordingNotificationManager()
  if (!manager) {
    return
  }

  void manager.hide()
}

const addRecordingNotificationListenerSafely = (
  ...args: Parameters<RecordingNotificationManagerType['addEventListener']>
) => {
  const manager = getRecordingNotificationManager()
  if (!manager) {
    return noopNotificationSubscription
  }

  return manager.addEventListener(...args)
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

const getIosBundlePath = async (): Promise<string | null> => {
  if (!BundlePath?.getBundlePath) {
    return null
  }

  if (!iosBundlePathPromise) {
    iosBundlePathPromise = BundlePath.getBundlePath()
      .then((bundlePath) => bundlePath || null)
      .catch((error) => {
        console.error('Failed to resolve iOS bundle path:', error)
        return null
      })
  }

  return iosBundlePathPromise
}

const resolveCueSoundPath = async (soundFileName: string): Promise<string> => {
  if (Platform.OS !== 'ios') {
    return soundFileName
  }

  const bundlePath = await getIosBundlePath()
  if (!bundlePath) {
    return soundFileName
  }

  return `${bundlePath}/${soundFileName}`
}

const loadCueSoundBuffer = async (
  soundName: keyof typeof cueSoundAssets
): Promise<AudioBuffer> => {
  const cachedSoundBuffer = cueSoundBuffers[soundName]
  if (cachedSoundBuffer) {
    return cachedSoundBuffer
  }

  const cachedSoundBufferPromise = cueSoundBufferPromises[soundName]
  if (cachedSoundBufferPromise) {
    return cachedSoundBufferPromise
  }

  const soundBufferPromise = resolveCueSoundPath(cueSoundAssets[soundName])
    .then((cueSoundPath) => audioContext.decodeAudioData(cueSoundPath))
    .then((soundBuffer) => {
      cueSoundBuffers[soundName] = soundBuffer
      return soundBuffer
    })
    .finally(() => {
      cueSoundBufferPromises[soundName] = null
    })

  cueSoundBufferPromises[soundName] = soundBufferPromise
  return soundBufferPromise
}

const playCueSound = async (
  soundName: keyof typeof cueSoundAssets,
  waitUntilFinished: boolean = false,
  shouldContinue: () => boolean = () => true
) => {
  try {
    const soundBuffer = await loadCueSoundBuffer(soundName)
    if (!shouldContinue()) {
      return
    }

    await audioContext.resume()
    if (!shouldContinue()) {
      return
    }

    const source = audioContext.createBufferSource()
    source.buffer = soundBuffer
    source.connect(audioContext.destination)
    source.start()

    if (waitUntilFinished) {
      await wait(Math.ceil(soundBuffer.duration * 1000), shouldContinue)
    }
  } catch (error) {
    console.error(`Failed to play ${soundName} cue sound:`, error)
  }
}

export const AudioRecorder = () => {
  const { t } = useTranslation()
  const maxDurationSeconds = useConfigStore(
    // We add a buffer to avoid the recording from being rejected due to timing issues
    (state) => Math.max(state.maxDurationSeconds - 60, 0)
  )
  const [recorderPhase, setRecorderPhase] = useState<RecorderPhase>('idle')
  const [shouldResetNavigation, setShouldResetNavigation] = useState(false)
  const [recordingTimeMs, setRecordingTimeMs] = useState(0)
  const [permissionStatus, setPermissionStatus] =
    useState<PermissionStatus>('Undetermined')
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

  const recordingDurationInterval = useRef<ReturnType<
    typeof setInterval
  > | null>(null)

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

  const deactivateAudioSession = useCallback(async () => {
    try {
      await AudioManager.setAudioSessionActivity(false)
    } catch (error) {
      console.error('Failed to deactivate the audio session:', error)
    }
  }, [])

  const enableRecorderFileOutput = useCallback(() => {
    try {
      const result = audioRecorder.enableFileOutput({
        format: FileFormat.M4A,
        preset: FilePreset.High,
        directory: FileDirectory.Document,
        subDirectory: 'Assistant Transcripts',
      })

      if (result.status === 'error') {
        console.warn(result.message)
      }
    } catch (error) {
      console.error('Failed to enable recorder file output:', error)
    }
  }, [])

  const disableRecorderFileOutput = useCallback(() => {
    try {
      audioRecorder.disableFileOutput()
    } catch (error) {
      console.error('Failed to disable recorder file output:', error)
    }
  }, [])

  const stopRecorderIfNeeded = useCallback(
    (options?: { force?: boolean; updateState?: boolean }): string | null => {
      const force = options?.force ?? false
      const updateState = options?.updateState ?? true
      if (!force && !RECORDING_PHASES.has(recorderPhaseRef.current)) {
        return null
      }

      try {
        const result = audioRecorder.stop()
        if (
          result.status === 'error' &&
          !result.message.includes('Recorder is not in recording state.')
        ) {
          console.warn(result.message)
          return null
        }
        return result.status === 'success' ? result.path : null
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
    [setRecorderPhaseState]
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

  const showRecordingNotification = useCallback(
    async (paused: boolean) => {
      await showRecordingNotificationSafely({
        title: t('home.recordingNotificationTitle'),
        contentText: t(
          paused
            ? 'home.recordingNotificationPaused'
            : 'home.recordingNotificationRecording'
        ),
        paused,
        smallIconResourceName: 'logo',
        pauseIconResourceName: 'pause',
        resumeIconResourceName: 'resume',
        color: 0xff6200,
      })
    },
    [t]
  )

  const clearRecording = useCallback(
    async (options?: { updateState?: boolean; clearFile?: boolean }) => {
      const updateState = options?.updateState ?? true
      invalidateLifecycle()

      await enqueueRecorderAction(async () => {
        const stoppedRecordingPath = stopRecorderIfNeeded({
          force: true,
          updateState,
        })
        stopAutoStopHaptics()
        hideRecordingNotificationSafely()
        hasReachedMaxDuration.current = false
        recordingStartDateTime.current = null
        if (recordingDurationInterval.current) {
          clearInterval(recordingDurationInterval.current)
          recordingDurationInterval.current = null
        }
        if (updateState && isMountedRef.current) {
          setRecordingTimeMs(0)
        }
        const localRecordingPath = stoppedRecordingPath
        if (options?.clearFile && localRecordingPath) {
          try {
            await deleteLocalRecordingFile(localRecordingPath)
          } catch (error) {
            console.error('Failed to delete local discarded recording:', error)
          }
        }
        disableRecorderFileOutput()
        await deactivateAudioSession()
      })
    },
    [
      deactivateAudioSession,
      disableRecorderFileOutput,
      invalidateLifecycle,
      stopAutoStopHaptics,
      stopRecorderIfNeeded,
    ]
  )

  useEffect(() => {
    isMountedRef.current = true
    AudioManager.requestRecordingPermissions()
      .then((res) => {
        if (!isMountedRef.current) {
          return
        }
        setPermissionStatus(res)
        if (res === 'Granted') {
          enableRecorderFileOutput()
        }
      })
      .catch((error) => {
        console.error('Failed to request recording permissions:', error)
      })

    return () => {
      isMountedRef.current = false
      stopAutoStopHaptics()
      void clearRecording({ updateState: false })
    }
  }, [clearRecording, enableRecorderFileOutput, stopAutoStopHaptics])

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
      if (recordingDurationInterval.current) {
        clearInterval(recordingDurationInterval.current)
        recordingDurationInterval.current = null
      }
      return
    }

    if (!recordingDurationInterval.current) {
      recordingDurationInterval.current = setInterval(() => {
        try {
          const duration = audioRecorder.getCurrentDuration()
          setRecordingTimeMs(duration * 1000)
        } catch (error) {
          console.error('Failed to get current recording duration:', error)
        }
      }, 200)
    }

    return () => {
      if (recordingDurationInterval.current) {
        clearInterval(recordingDurationInterval.current)
        recordingDurationInterval.current = null
      }
    }
  }, [shouldPollRecordingDuration])

  const handleStartRecording = useCallback(async () => {
    if (recorderPhaseRef.current !== 'idle') {
      return
    }

    const lifecycleToken = beginLifecycleAction('starting')

    await enqueueRecorderAction(async () => {
      if (!isCurrentLifecycle(lifecycleToken)) {
        return
      }

      let shouldDeactivateAudioSession = false
      try {
        const permissions = await AudioManager.requestRecordingPermissions()
        if (!isCurrentLifecycle(lifecycleToken)) {
          return
        }
        setPermissionStatus(permissions)

        if (permissions !== 'Granted') {
          console.warn('Permissions are not granted')
          setRecorderPhaseIfCurrent(lifecycleToken, 'idle')
          return
        }

        const success = await AudioManager.setAudioSessionActivity(true)
        if (!isCurrentLifecycle(lifecycleToken)) {
          if (success) {
            await deactivateAudioSession()
          }
          return
        }
        if (!success) {
          console.warn('Could not activate the audio session')
          setRecorderPhaseIfCurrent(lifecycleToken, 'idle')
          return
        }
        shouldDeactivateAudioSession = true

        await playCueSound('start', true, () =>
          isCurrentLifecycle(lifecycleToken)
        )
        if (!isCurrentLifecycle(lifecycleToken)) {
          return
        }

        const result = audioRecorder.start()
        if (result.status === 'error') {
          console.warn(result.message)
          setRecorderPhaseIfCurrent(lifecycleToken, 'idle')
          return
        }
        await showRecordingNotification(false)

        shouldDeactivateAudioSession = false
        hasReachedMaxDuration.current = false
        recordingStartDateTime.current = new Date()

        if (isCurrentLifecycle(lifecycleToken)) {
          setRecordingTimeMs(0)
          setRecorderPhaseState('recording')
        } else {
          stopRecorderIfNeeded({ force: true, updateState: false })
          await deactivateAudioSession()
        }
      } catch (error) {
        console.error('Failed to start recording:', error)
        setRecorderPhaseIfCurrent(lifecycleToken, 'idle')
      } finally {
        if (shouldDeactivateAudioSession) {
          await deactivateAudioSession()
        }
      }
    })
  }, [
    beginLifecycleAction,
    deactivateAudioSession,
    isCurrentLifecycle,
    setRecorderPhaseIfCurrent,
    setRecorderPhaseState,
    showRecordingNotification,
    stopRecorderIfNeeded,
  ])

  useEffect(() => {
    if (permissionStatus === 'Granted' && !hasAutoStartedRef.current) {
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
        await playCueSound('end', true, () =>
          isCurrentLifecycle(lifecycleToken)
        )
        await showRecordingNotification(true)
        setRecorderPhaseIfCurrent(lifecycleToken, 'paused')
      } catch (error) {
        console.error('Failed to pause recording:', error)
        setRecorderPhaseIfCurrent(lifecycleToken, 'recording')
      }
    })
  }, [
    beginLifecycleAction,
    isCurrentLifecycle,
    setRecorderPhaseIfCurrent,
    showRecordingNotification,
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
        await playCueSound('start', true, () =>
          isCurrentLifecycle(lifecycleToken)
        )
        if (!isCurrentLifecycle(lifecycleToken)) {
          return
        }

        audioRecorder.resume()
        await showRecordingNotification(false)
        setRecorderPhaseIfCurrent(lifecycleToken, 'recording')
      } catch (error) {
        console.error('Failed to resume recording:', error)
        setRecorderPhaseIfCurrent(lifecycleToken, 'paused')
      }
    })
  }, [
    beginLifecycleAction,
    isCurrentLifecycle,
    setRecorderPhaseIfCurrent,
    showRecordingNotification,
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

        const result = audioRecorder.stop()
        hideRecordingNotificationSafely()
        if (result.status === 'error') {
          if (result.message.includes('Recorder is not in recording state.')) {
            setRecorderPhaseIfCurrent(lifecycleToken, 'idle')
          } else {
            console.warn(result.message)
            setRecorderPhaseIfCurrent(lifecycleToken, previousPhase)
          }
          return false
        }

        if (!wasPaused) {
          await playCueSound('end', true, () =>
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
          duration_seconds: result.duration,
          filePath: result.path,
          title,
          id: uuid.v4(),
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
    beginLifecycleAction,
    deactivateAudioSession,
    isCurrentLifecycle,
    setRecorderPhaseIfCurrent,
    setRecorderPhaseState,
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
    const pauseListener = addRecordingNotificationListenerSafely(
      'recordingNotificationPause',
      () => {
        onPauseRecord()
      }
    )

    const resumeListener = addRecordingNotificationListenerSafely(
      'recordingNotificationResume',
      () => {
        onResumeRecord()
      }
    )

    return () => {
      pauseListener.remove()
      resumeListener.remove()
      hideRecordingNotificationSafely()
    }
  }, [onPauseRecord, onResumeRecord])

  useEffect(() => {
    if (permissionStatus === 'Denied') {
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

  if (permissionStatus === 'Denied') {
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
