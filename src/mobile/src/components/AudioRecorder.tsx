import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  Button,
  Linking,
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
  FileFormat,
  FilePreset,
  RecordingNotificationManager,
} from 'react-native-audio-api'
import { trigger as triggerHaptic } from 'react-native-haptic-feedback'
import { formatDuration } from '@/features/recordings/utils/formatDuration'
import { useNavigation, usePreventRemove } from '@react-navigation/core'
import { PermissionStatus } from 'react-native-audio-api/lib/typescript/system/types'
import uuid from 'react-native-uuid'
import { useLocalRecordings } from '@/features/recordings/hooks/useLocalRecordings'
import { AppText } from './AppText'
import { colors } from './colors'
import { useResetNavigationHistory } from '@/navigation/useRestNavigationHistory'
// @ts-expect-error SVG
import PauseIcon from '@/assets/icons/pause-recording.svg'
// @ts-expect-error SVG
import StopIcon from '@/assets/icons/stop-recording.svg'
// @ts-expect-error SVG
import PlayIcon from '@/assets/icons/resume-recording.svg'
import { useConfigStore } from '@/services/configStore'
// @ts-expect-error audio asset
import startSound from '@/assets/sounds/start.wav'
// @ts-expect-error audio asset
import endSound from '@/assets/sounds/end.wav'

AudioManager.setAudioSessionOptions({
  iosCategory: 'playAndRecord',
  iosMode: 'default',
  iosOptions: ['defaultToSpeaker'],
})

const audioRecorder = new AudioRecorderApi()
const audioContext = new AudioContext()
const cueSoundAssets = {
  start: startSound,
  end: endSound,
} as const
const cueSoundBuffers: Record<keyof typeof cueSoundAssets, AudioBuffer | null> =
  {
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

const showRecordingNotificationSafely = async (
  ...args: Parameters<typeof RecordingNotificationManager.show>
) => {
  if (!isAndroid) {
    return
  }

  await RecordingNotificationManager.show(...args)
}

const hideRecordingNotificationSafely = () => {
  if (!isAndroid) {
    return
  }

  void RecordingNotificationManager.hide()
}

const addRecordingNotificationListenerSafely = (
  ...args: Parameters<typeof RecordingNotificationManager.addEventListener>
) => {
  if (!isAndroid) {
    return noopNotificationSubscription
  }

  return RecordingNotificationManager.addEventListener(...args)
}

const waitForNextFrame = () =>
  new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      resolve()
    })
  })

const wait = (durationMs: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, durationMs)
  })

const loadCueSoundBuffer = async (
  soundName: keyof typeof cueSoundAssets
): Promise<AudioBuffer> => {
  if (!cueSoundBuffers[soundName]) {
    cueSoundBuffers[soundName] = await audioContext.decodeAudioData(
      cueSoundAssets[soundName]
    )
  }

  return cueSoundBuffers[soundName]!
}

const playCueSound = async (
  soundName: keyof typeof cueSoundAssets,
  waitUntilFinished: boolean = false
) => {
  try {
    const soundBuffer = await loadCueSoundBuffer(soundName)
    await audioContext.resume()

    const source = audioContext.createBufferSource()
    source.buffer = soundBuffer
    source.connect(audioContext.destination)
    source.start()

    if (waitUntilFinished) {
      await wait(Math.ceil(soundBuffer.duration * 1000))
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
  const [isRecording, setIsRecording] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [shouldResetNavigation, setShouldResetNavigation] = useState(false)
  const [recordingTimeMs, setRecordingTimeMs] = useState(0)
  const [permissionStatus, setPermissionStatus] =
    useState<PermissionStatus>('Undetermined')
  const { addRecording } = useLocalRecordings()
  const resetNavigationHistory = useResetNavigationHistory()
  const navigation = useNavigation()
  const recordingStartDateTime = useRef<Date | null>(null)
  const autoStopHapticsInterval = useRef<ReturnType<typeof setInterval> | null>(
    null
  )
  const hasReachedMaxDuration = useRef(false)

  const recordTimeLabel = useMemo(
    () => formatDuration(recordingTimeMs),
    [recordingTimeMs]
  )

  const recordingDurationInterval = useRef<ReturnType<
    typeof setTimeout
  > | null>(null)

  const stopAutoStopHaptics = useCallback(() => {
    if (autoStopHapticsInterval.current) {
      clearInterval(autoStopHapticsInterval.current)
      autoStopHapticsInterval.current = null
    }
  }, [])

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

  const clearRecording = useCallback(() => {
    audioRecorder.stop()
    audioRecorder.disableFileOutput()
    AudioManager.setAudioSessionActivity(false)
    hideRecordingNotificationSafely()
    // Todo delete file as option for when going back alert
  }, [])

  useEffect(() => {
    AudioManager.requestRecordingPermissions().then((res) => {
      setPermissionStatus(res)
      if (res === 'Granted') {
        audioRecorder.enableFileOutput({
          format: FileFormat.M4A,
          preset: FilePreset.High,
        })
      }
    })

    return () => {
      stopAutoStopHaptics()
      clearRecording()
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
            clearRecording()
            setIsRecording(false)
            setIsPaused(false)
            setRecordingTimeMs(0)
            navigation.dispatch(data.action)
            // And we reset the navigation history to the main screen too
            resetNavigationHistory('Main')
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
    if (!isRecording || isPaused) {
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
      }
    }
  }, [isPaused, isRecording])

  const handleStartRecording = useCallback(async () => {
    const permissions = await AudioManager.requestRecordingPermissions()
    if (permissions !== 'Granted') {
      console.warn('Permissions are not granted')
      return
    }

    setIsLoading(true)
    try {
      const success = await AudioManager.setAudioSessionActivity(true)
      if (!success) {
        console.warn('Could not activate the audio session')
        return
      }

      await playCueSound('start', true)
      const result = audioRecorder.start()
      if (result.status === 'error') {
        console.warn(result.message)
        return
      }

      await showRecordingNotification(false)
      setRecordingTimeMs(0)
      setIsRecording(true)
      setIsPaused(false)
      hasReachedMaxDuration.current = false
      recordingStartDateTime.current = new Date()
    } catch (error) {
      console.error('Failed to start recording:', error)
    } finally {
      setIsLoading(false)
    }
  }, [showRecordingNotification])

  useEffect(() => {
    if (permissionStatus === 'Granted') {
      handleStartRecording()
    }
  }, [permissionStatus, handleStartRecording])

  const onPauseRecord = useCallback(async () => {
    setIsLoading(true)
    try {
      audioRecorder.pause()
      await playCueSound('end', true)
      setIsPaused(true)
      await showRecordingNotification(true)
    } catch (error) {
      console.error('Failed to pause recording:', error)
    } finally {
      setIsLoading(false)
    }
  }, [showRecordingNotification])

  const onResumeRecord = useCallback(async () => {
    setIsLoading(true)
    try {
      await playCueSound('start', true)
      audioRecorder.resume()
      await showRecordingNotification(false)
      setIsPaused(false)
    } catch (error) {
      console.error('Failed to resume recording:', error)
    } finally {
      setIsLoading(false)
    }
  }, [showRecordingNotification])

  const onStopRecord = useCallback(async () => {
    setIsLoading(true)
    setIsStopping(true)
    try {
      await waitForNextFrame()
      const result = audioRecorder.stop()
      hideRecordingNotificationSafely()
      if (result.status === 'error') {
        console.warn(result.message)
        setIsStopping(false)
        return false
      }

      if (!isPaused) {
        await playCueSound('end', true)
      }
      await AudioManager.setAudioSessionActivity(false)

      const title = `${t('home.recordingPrefix')} ${t(
        'shared.utils.formatDateTimeStatic',
        { value: recordingStartDateTime.current! }
      )}`
      addRecording({
        created_at: recordingStartDateTime.current!.toISOString(),
        duration_seconds: result.duration,
        filePath: result.paths[0],
        title,
        id: uuid.v4(),
        uploadingStatus: 'to_upload',
      })

      setRecordingTimeMs(0)
      setIsRecording(false)
      setIsPaused(false)
      setShouldResetNavigation(true)
      return true
    } catch (error) {
      console.error('Failed to stop recording:', error)
      setIsStopping(false)
      return false
    } finally {
      setIsLoading(false)
    }
  }, [addRecording, isPaused, t])

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
        if (didStop) {
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

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const onClearRecord = useCallback(async () => {
    setIsLoading(true)
    Alert.alert(t('recordings.deleteTitle'), t('recordings.deleteMessage'), [
      {
        style: 'cancel',
        text: t('recordings.deleteCancel'),
        onPress: () => {
          setIsLoading(false)
        },
      },
      {
        style: 'destructive',
        text: t('recordings.deleteConfirm'),
        onPress: async () => {
          try {
            audioRecorder.stop()
            setIsRecording(false)
            setIsPaused(false)
            setRecordingTimeMs(0)
          } finally {
            setIsLoading(false)
          }
        },
      },
    ])
  }, [t])

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
          onPress={isPaused ? onResumeRecord : onPauseRecord}
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
          onPress={onStopRecord}
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
