import { useConfig } from '@/api/useConfig.ts'
import {
  AudioInputManager,
  IndexedDbChunkStore,
  RecorderLifecycleState,
  RecorderManager,
  StoredRecording,
} from '@/features/recordings/recorder'
import { useLocalRecordingsStore } from '@/features/recordings/store/useLocalRecordingsStore.ts'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

const PREFERRED_MIME_TYPES = [
  'audio/ogg;codecs=opus',
  'audio/webm;codecs=opus',
  'audio/mp4',
  'audio/webm',
]

const getExtensionFromMimeType = (mimeType: string) => {
  if (mimeType.includes('ogg')) {
    return 'ogg'
  }
  if (mimeType.includes('mp4')) {
    return 'mp4'
  }
  return 'webm'
}

const RECORDING_CHUNK_TIMESLICE_MS = 10_000
const MIN_FREE_BYTES = 5 * 1024 * 1024

type RecordingControllerState = {
  recorderState: RecorderLifecycleState
  selectedAudioInputId: string
  audioInputs: MediaDeviceInfo[]
  recordingDurationMs: number
  analyserNode: AnalyserNode | null
  recordingError: string | null
  currentRecordingId: string | null
}

type RecordingController = RecordingControllerState & {
  canPauseOrStop: boolean
  isPaused: boolean
  startRecording: () => Promise<void>
  pauseRecording: () => Promise<void>
  resumeRecording: () => Promise<void>
  stopAndDispose: () => Promise<void>
  switchAudioInput: (deviceId: string) => Promise<void>
}

export const useRecordingController = (
  autoStart = false
): RecordingController => {
  const { t } = useTranslation(['record'])
  const { data: appConfig } = useConfig()
  const chunkStoreRef = useRef<IndexedDbChunkStore | null>(null)
  const audioInputManagerRef = useRef<AudioInputManager | null>(null)
  const recorderRef = useRef<RecorderManager | null>(null)
  const activeRecordingIdRef = useRef<string | null>(null)
  const durationTimerRef = useRef<number | null>(null)
  const startedAtRef = useRef<number | null>(null)
  const accumulatedDurationMsRef = useRef(0)
  const autoSplitInFlightRef = useRef(false)
  const isUnmountedRef = useRef(false)
  const lowStorageAlertShownRef = useRef(false)

  const [state, setState] = useState<RecordingControllerState>({
    recorderState: 'idle',
    selectedAudioInputId: '',
    audioInputs: [],
    recordingDurationMs: 0,
    analyserNode: null,
    recordingError: null,
    currentRecordingId: null,
  })

  const ensureManagers = useCallback(() => {
    if (isUnmountedRef.current) {
      return
    }

    if (
      chunkStoreRef.current &&
      audioInputManagerRef.current &&
      recorderRef.current &&
      !recorderRef.current.isDisposed()
    ) {
      return
    }

    const chunkStore = new IndexedDbChunkStore()
    const audioInputManager = new AudioInputManager()
    const recorder = new RecorderManager(audioInputManager, {
      onChunk: async (chunk) => {
        const recordingId = activeRecordingIdRef.current
        if (!recordingId) {
          return
        }

        await chunkStore.saveChunk(
          chunk.blob,
          chunk.sequenceNumber,
          chunk.timestamp,
          recordingId
        )

        useLocalRecordingsStore.getState().updateRecording(recordingId, {
          chunkCount: chunk.sequenceNumber + 1,
          totalBytes:
            (useLocalRecordingsStore.getState().getRecordingById(recordingId)
              ?.totalBytes ?? 0) + chunk.blob.size,
        })
      },
      onStateChange: (recorderState) => {
        setState((current) => ({ ...current, recorderState }))

        const activeId = activeRecordingIdRef.current
        if (
          activeId &&
          (recorderState === 'recording' || recorderState === 'paused')
        ) {
          useLocalRecordingsStore.getState().updateRecording(activeId, {
            status: recorderState,
          })
        }

        if (recorderState === 'recording') {
          if (startedAtRef.current === null) {
            startedAtRef.current = Date.now()
          }

          if (durationTimerRef.current === null) {
            durationTimerRef.current = window.setInterval(() => {
              const startedAt = startedAtRef.current
              const runningDuration = startedAt ? Date.now() - startedAt : 0
              const durationMs =
                accumulatedDurationMsRef.current + runningDuration

              if (activeId) {
                useLocalRecordingsStore.getState().updateRecording(activeId, {
                  durationMs,
                })
              }

              setState((currentState) => ({
                ...currentState,
                recordingDurationMs: durationMs,
              }))
            }, 250)
          }
          return
        }

        if (startedAtRef.current !== null) {
          accumulatedDurationMsRef.current += Date.now() - startedAtRef.current
          startedAtRef.current = null
        }

        if (durationTimerRef.current !== null) {
          window.clearInterval(durationTimerRef.current)
          durationTimerRef.current = null
        }

        if (activeId && recorderState === 'stopped') {
          useLocalRecordingsStore.getState().updateRecording(activeId, {
            status: 'stopped',
            durationMs: accumulatedDurationMsRef.current,
          })
        }

        setState((currentState) => ({
          ...currentState,
          recordingDurationMs: accumulatedDurationMsRef.current,
        }))
      },
      onError: (error) => {
        setState((current) => ({
          ...current,
          recordingError: error.message,
        }))
      },
    })

    chunkStoreRef.current = chunkStore
    audioInputManagerRef.current = audioInputManager
    recorderRef.current = recorder
  }, [])

  useEffect(() => {
    isUnmountedRef.current = false
    ensureManagers()

    const chunkStore = chunkStoreRef.current!
    const audioInputManager = audioInputManagerRef.current!

    let active = true
    void (async () => {
      try {
        await chunkStore.openDatabase()
      } catch (error) {
        if (!active) {
          return
        }
        console.error('Failed to open recordings IndexedDB database', error)
        setState((current) => ({
          ...current,
          recordingError: 'Failed to initialize local recording storage.',
        }))
      }
    })()

    const unsubscribeAudioInputs = audioInputManager.subscribe((devices) => {
      setState((current) => {
        const selectedAudioInputId =
          current.selectedAudioInputId &&
          devices.some((d) => d.deviceId === current.selectedAudioInputId)
            ? current.selectedAudioInputId
            : (devices[0]?.deviceId ?? '')

        return {
          ...current,
          selectedAudioInputId,
          audioInputs: devices,
        }
      })
    })

    return () => {
      isUnmountedRef.current = true
      active = false
      unsubscribeAudioInputs()
      if (durationTimerRef.current !== null) {
        window.clearInterval(durationTimerRef.current)
      }

      const recorder = recorderRef.current
      const audioInputManager = audioInputManagerRef.current

      recorderRef.current = null
      audioInputManagerRef.current = null
      chunkStoreRef.current = null

      void recorder?.dispose()
      audioInputManager?.dispose()
    }
  }, [ensureManagers])

  useEffect(() => {
    const flushCurrentChunk = () => {
      const recorder = recorderRef.current
      if (!recorder) {
        return
      }
      recorder.requestDataFlush()
      void recorder.flushPendingChunks()
    }

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        flushCurrentChunk()
      }
    }

    window.addEventListener('pagehide', flushCurrentChunk)
    window.addEventListener('beforeunload', flushCurrentChunk)
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      window.removeEventListener('pagehide', flushCurrentChunk)
      window.removeEventListener('beforeunload', flushCurrentChunk)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [])

  const startRecording = useCallback(async () => {
    if (isUnmountedRef.current) {
      return
    }

    ensureManagers()
    if (isUnmountedRef.current) {
      return
    }

    const chunkStore = chunkStoreRef.current
    const audioInputManager = audioInputManagerRef.current
    const recorder = recorderRef.current
    if (!chunkStore || !audioInputManager || !recorder) {
      return
    }
    const isStaleRecorder = () =>
      isUnmountedRef.current ||
      recorderRef.current !== recorder ||
      recorder.isDisposed()

    accumulatedDurationMsRef.current = 0
    startedAtRef.current = null
    setState((current) => ({
      ...current,
      recorderState: 'starting',
      recordingDurationMs: 0,
      recordingError: null,
    }))

    const permissionState = await audioInputManager.getPermissionState()
    if (isStaleRecorder()) {
      return
    }
    if (permissionState === 'denied') {
      setState((current) => ({
        ...current,
        recorderState: 'idle',
        recordingError:
          'Microphone access is denied. Please allow microphone permission in your browser settings.',
      }))
      return
    }

    if (permissionState !== 'granted') {
      const granted = await audioInputManager.requestPermission()
      if (isStaleRecorder()) {
        return
      }
      if (!granted) {
        setState((current) => ({
          ...current,
          recorderState: 'idle',
          recordingError: 'Microphone access is required to start recording.',
        }))
        return
      }
    }

    if (isStaleRecorder()) {
      return
    }

    const recordingId = crypto.randomUUID()
    const createdAt = Date.now()
    const initialRecording: StoredRecording = {
      id: recordingId,
      createdAt,
      updatedAt: createdAt,
      mimeType: PREFERRED_MIME_TYPES[0],
      status: 'recording',
      chunkCount: 0,
      totalBytes: 0,
      durationMs: 0,
      uploadProgress: 0,
      uploadError: null,
      filename: '',
      source: 'web_recording',
    }
    useLocalRecordingsStore.getState().upsertRecording(initialRecording)

    activeRecordingIdRef.current = recordingId
    chunkStore.setActiveRecording(recordingId)
    setState((current) => ({
      ...current,
      currentRecordingId: recordingId,
    }))

    try {
      await recorder.start({
        preferredMimeTypes: PREFERRED_MIME_TYPES,
        timesliceMs: RECORDING_CHUNK_TIMESLICE_MS,
        deviceId: state.selectedAudioInputId || undefined,
      })
      if (isStaleRecorder()) {
        await chunkStore.clearRecording(recordingId)
        useLocalRecordingsStore.getState().removeRecording(recordingId)
        if (activeRecordingIdRef.current === recordingId) {
          activeRecordingIdRef.current = null
        }
        setState((current) =>
          current.currentRecordingId === recordingId
            ? { ...current, currentRecordingId: null, analyserNode: null }
            : current
        )
        return
      }
      setState((current) => ({
        ...current,
        analyserNode: recorder.getAnalyserNode(),
      }))

      const resolvedMimeType = recorder.getMimeType()
      if (!resolvedMimeType) {
        throw new Error('No supported MIME type found')
      }
      useLocalRecordingsStore.getState().updateRecording(recordingId, {
        mimeType: resolvedMimeType,
        status: 'recording',
        uploadProgress: 0,
        uploadError: null,
        // @ts-expect-error bad inference on formatDateTimeStatic
        filename: `${t('record:recordingPrefix')} ${t('shared:utils.formatDateTimeStatic', { value: createdAt })}.${getExtensionFromMimeType(resolvedMimeType)}`,
      })
    } catch (error) {
      if (isStaleRecorder()) {
        await chunkStore.clearRecording(recordingId)
        useLocalRecordingsStore.getState().removeRecording(recordingId)
        if (activeRecordingIdRef.current === recordingId) {
          activeRecordingIdRef.current = null
        }
        setState((current) =>
          current.currentRecordingId === recordingId
            ? { ...current, currentRecordingId: null, analyserNode: null }
            : current
        )
        return
      }
      setState((current) => ({
        ...current,
        recorderState: 'idle',
        analyserNode: null,
        recordingError:
          error instanceof Error ? error.message : 'Failed to start recording',
      }))
      await chunkStore.clearRecording(recordingId)
      useLocalRecordingsStore.getState().removeRecording(recordingId)
      activeRecordingIdRef.current = null
      setState((current) => ({
        ...current,
        currentRecordingId: null,
      }))
    }
  }, [ensureManagers, state.selectedAudioInputId, t])

  const autoStartedRef = useRef(false)
  useEffect(() => {
    if (!autoStart || autoStartedRef.current) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      if (autoStartedRef.current) {
        return
      }
      autoStartedRef.current = true
      void startRecording()
    }, 0)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [autoStart, startRecording])

  const pauseRecording = useCallback(async () => {
    const recorder = recorderRef.current
    const recordingId = activeRecordingIdRef.current
    if (!recorder || !recordingId) {
      return
    }
    await recorder.pause()
    useLocalRecordingsStore.getState().updateRecording(recordingId, {
      status: 'paused',
      durationMs: accumulatedDurationMsRef.current,
    })
  }, [])

  const resumeRecording = useCallback(async () => {
    const recorder = recorderRef.current
    const recordingId = activeRecordingIdRef.current
    if (!recorder || !recordingId) {
      return
    }
    await recorder.resume()
    useLocalRecordingsStore.getState().updateRecording(recordingId, {
      status: 'recording',
    })
  }, [])

  const switchAudioInput = useCallback(
    async (deviceId: string) => {
      ensureManagers()
      setState((current) => ({
        ...current,
        selectedAudioInputId: deviceId,
      }))

      const audioInputManager = audioInputManagerRef.current!
      const recorder = recorderRef.current!
      await audioInputManager.selectDevice(deviceId)

      if (
        recorder.getState() === 'recording' ||
        recorder.getState() === 'paused'
      ) {
        await recorder.switchInput(deviceId)
      }
    },
    [ensureManagers]
  )

  const stopRecording = useCallback(async () => {
    const recorder = recorderRef.current
    const recordingId = activeRecordingIdRef.current
    if (!recorder || !recordingId) {
      return
    }

    await recorder.stop()

    if (startedAtRef.current !== null) {
      accumulatedDurationMsRef.current += Date.now() - startedAtRef.current
      startedAtRef.current = null
    }

    useLocalRecordingsStore.getState().updateRecording(recordingId, {
      status: 'stopped',
      durationMs: accumulatedDurationMsRef.current,
    })

    activeRecordingIdRef.current = null
    setState((current) => ({
      ...current,
      currentRecordingId: null,
      analyserNode: null,
    }))
  }, [])

  const maxDurationMs = useMemo(() => {
    const maxDurationSeconds =
      appConfig?.audio_recording?.max_duration_seconds ??
      Number.POSITIVE_INFINITY
    return maxDurationSeconds > 0
      ? maxDurationSeconds * 1000
      : Number.POSITIVE_INFINITY
  }, [appConfig?.audio_recording?.max_duration_seconds])

  useEffect(() => {
    if (state.recorderState !== 'recording') {
      lowStorageAlertShownRef.current = false
      return
    }
    const checkAvailableStorage = async () => {
      if (!navigator.storage?.estimate) {
        return
      }

      try {
        const { usage = 0, quota = 0 } = await navigator.storage.estimate()
        const remaining = quota - usage

        if (
          remaining > 0 &&
          remaining < MIN_FREE_BYTES &&
          !lowStorageAlertShownRef.current
        ) {
          lowStorageAlertShownRef.current = true
          await stopRecording()
          window.alert(t('record:alerts.lowStorage'))
        }
      } catch (error) {
        console.error('Failed to estimate storage.', error)
      }
    }

    void checkAvailableStorage()
    const intervalId = window.setInterval(() => {
      void checkAvailableStorage()
    }, 5000)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [state.recorderState, stopRecording, t])

  useEffect(() => {
    if (
      state.recorderState !== 'recording' ||
      !Number.isFinite(maxDurationMs) ||
      state.recordingDurationMs < maxDurationMs ||
      autoSplitInFlightRef.current
    ) {
      return
    }

    const recordingIdToClose = activeRecordingIdRef.current
    if (!recordingIdToClose) {
      return
    }

    autoSplitInFlightRef.current = true
    void (async () => {
      await stopRecording()
      await startRecording()
    })().finally(() => {
      autoSplitInFlightRef.current = false
    })
  }, [
    maxDurationMs,
    startRecording,
    state.recordingDurationMs,
    state.recorderState,
    stopRecording,
  ])

  const stopAndDispose = useCallback(async () => {
    const recorder = recorderRef.current
    const audioInputManager = audioInputManagerRef.current
    if (!recorder) {
      audioInputManager?.dispose()
      audioInputManagerRef.current = null
      return
    }

    let stopError: unknown = null
    try {
      await stopRecording()
    } catch (error) {
      stopError = error
      console.error('Failed to stop recorder cleanly, forcing dispose', error)
    } finally {
      await recorder.dispose()
      recorderRef.current = null
      audioInputManager?.dispose()
      audioInputManagerRef.current = null
    }

    if (stopError) {
      setState((current) => ({
        ...current,
        recorderState: 'idle',
        analyserNode: null,
        recordingError:
          stopError instanceof Error
            ? stopError.message
            : 'Failed to stop recording cleanly',
      }))
    }
  }, [stopRecording])

  return useMemo(() => {
    const canPauseOrStop =
      state.recorderState === 'recording' || state.recorderState === 'paused'

    return {
      ...state,
      canPauseOrStop,
      isPaused: state.recorderState === 'paused',
      startRecording,
      pauseRecording,
      resumeRecording,
      stopAndDispose,
      switchAudioInput,
    }
  }, [
    pauseRecording,
    resumeRecording,
    startRecording,
    state,
    stopAndDispose,
    switchAudioInput,
  ])
}
