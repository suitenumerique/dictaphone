import { keys } from '@/api/queryKeys.ts'
import {
  createPendingAudioFile,
  markUploadEnded,
} from '@/features/files/api/createFile.ts'
import {
  AudioInputManager,
  IndexedDbChunkStore,
  RecorderLifecycleState,
  RecorderManager,
  StoredRecording,
  UploadStreamManager,
} from '@/features/recordings/recorder'
import {
  selectLatestRecoverableRecording,
  useLocalRecordingsStore,
} from '@/features/recordings/store/useLocalRecordingsStore.ts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiFileItem } from '@/features/files/api/types'
import { useTranslation } from 'react-i18next'

const PREFERRED_MIME_TYPES = [
  'audio/ogg;codecs=opus',
  'audio/webm;codecs=opus',
  'audio/mp4',
  'audio/webm',
]
const RECORDING_CHUNK_TIMESLICE_MS = 10_000

const getExtensionFromMimeType = (mimeType: string) => {
  if (mimeType.includes('ogg')) {
    return 'ogg'
  }
  if (mimeType.includes('mp4')) {
    return 'mp4'
  }
  return 'webm'
}

type RecordingControllerState = {
  recorderState: RecorderLifecycleState
  selectedAudioInputId: string
  audioInputs: MediaDeviceInfo[]
  recordingDurationMs: number
  analyserNode: AnalyserNode | null
  uploadProgress: number
  uploadError: string | null
  recordingError: string | null
  currentRecordingId: string | null
  isUploading: boolean
}

type RecordingController = RecordingControllerState & {
  canPauseOrStop: boolean
  isPaused: boolean
  hasRecoverableRecording: boolean
  recoverableRecording: StoredRecording | null
  startRecording: () => Promise<void>
  pauseRecording: () => Promise<void>
  resumeRecording: () => Promise<void>
  stopRecording: () => Promise<void>
  switchAudioInput: (deviceId: string) => Promise<void>
  uploadCurrentRecording: () => Promise<ApiFileItem | undefined>
  downloadCurrentRecording: () => Promise<File | undefined>
  clearRecoverableRecording: () => Promise<void>
}

export const useRecordingController = (
  autoStart = false
): RecordingController => {
  const queryClient = useQueryClient()
  const recoverableRecording = useLocalRecordingsStore(
    selectLatestRecoverableRecording
  )
  const chunkStoreRef = useRef<IndexedDbChunkStore | null>(null)
  const audioInputManagerRef = useRef<AudioInputManager | null>(null)
  const uploadManagerRef = useRef<UploadStreamManager | null>(null)
  const recorderRef = useRef<RecorderManager | null>(null)
  const activeRecordingIdRef = useRef<string | null>(null)
  const uploadAbortControllerRef = useRef<AbortController | null>(null)
  const durationTimerRef = useRef<number | null>(null)
  const startedAtRef = useRef<number | null>(null)
  const accumulatedDurationMsRef = useRef(0)

  const [state, setState] = useState<RecordingControllerState>({
    recorderState: 'idle',
    selectedAudioInputId: '',
    audioInputs: [],
    recordingDurationMs: 0,
    analyserNode: null,
    uploadProgress: 0,
    uploadError: null,
    recordingError: null,
    currentRecordingId: null,
    isUploading: false,
  })

  const ensureManagers = useCallback(() => {
    if (
      chunkStoreRef.current &&
      audioInputManagerRef.current &&
      recorderRef.current
    ) {
      return
    }

    const chunkStore = new IndexedDbChunkStore()
    const audioInputManager = new AudioInputManager()
    const uploadManager = new UploadStreamManager(chunkStore)

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
    uploadManagerRef.current = uploadManager
    recorderRef.current = recorder
  }, [])

  useEffect(() => {
    ensureManagers()

    const chunkStore = chunkStoreRef.current!
    const audioInputManager = audioInputManagerRef.current!

    void chunkStore.openDatabase()

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
      unsubscribeAudioInputs()
      if (durationTimerRef.current !== null) {
        window.clearInterval(durationTimerRef.current)
      }
      uploadAbortControllerRef.current?.abort()
      void recorderRef.current?.dispose()
      audioInputManagerRef.current?.dispose()
    }
  }, [ensureManagers])

  useEffect(() => {
    const flushCurrentChunk = () => {
      console.info('Flushing current changers chunk.')
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
    ensureManagers()
    const chunkStore = chunkStoreRef.current!
    const audioInputManager = audioInputManagerRef.current!
    const recorder = recorderRef.current!

    accumulatedDurationMsRef.current = 0
    startedAtRef.current = null
    setState((current) => ({
      ...current,
      recordingDurationMs: 0,
      uploadProgress: 0,
      uploadError: null,
      recordingError: null,
    }))

    const permissionState = await audioInputManager.getPermissionState()
    if (permissionState === 'denied') {
      setState((current) => ({
        ...current,
        recordingError:
          'Microphone access is denied. Please allow microphone permission in your browser settings.',
      }))
      return
    }

    if (permissionState !== 'granted') {
      const granted = await audioInputManager.requestPermission()
      if (!granted) {
        setState((current) => ({
          ...current,
          recordingError: 'Microphone access is required to start recording.',
        }))
        return
      }
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
      })
    } catch (error) {
      setState((current) => ({
        ...current,
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
  }, [ensureManagers, state.selectedAudioInputId])

  const autoStartedRef = useRef(false)
  useEffect(() => {
    if (autoStart && !autoStartedRef.current) {
      autoStartedRef.current = true
      void startRecording()
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
  }, [])

  const { t } = useTranslation(['record', 'shared'])
  const uploadCurrentRecording = useCallback(async () => {
    const uploadManager = uploadManagerRef.current
    const chunkStore = chunkStoreRef.current
    if (!uploadManager || !chunkStore) {
      return
    }

    const recordingId =
      activeRecordingIdRef.current ?? recoverableRecording?.id ?? null
    if (!recordingId || uploadManager.isUploading(recordingId)) {
      return
    }

    const recording = useLocalRecordingsStore
      .getState()
      .getRecordingById(recordingId)
    if (!recording) {
      return
    }

    uploadAbortControllerRef.current?.abort()
    const abortController = new AbortController()
    uploadAbortControllerRef.current = abortController

    setState((current) => ({
      ...current,
      isUploading: true,
      uploadProgress: 0,
      uploadError: null,
      recordingError: null,
    }))

    useLocalRecordingsStore.getState().updateRecording(recordingId, {
      status: 'uploading',
    })

    try {
      const createdAtIso = new Date(recording.createdAt).toISOString()
      const durationSeconds = Math.max(0, recording.durationMs / 1000)

      const filename = `${t('record:recordingPrefix')} ${t('shared:utils.formatDateTimeStatic', { value: recording.createdAt })}.${getExtensionFromMimeType(recording.mimeType)}`

      const pendingFile = await createPendingAudioFile({
        filename,
        durationSeconds,
        createdAt: createdAtIso,
      })

      await uploadManager.uploadRecording({
        recordingId,
        url: pendingFile.policy,
        method: 'PUT',
        totalBytes: recording.totalBytes,
        contentType: recording.mimeType || 'audio/webm',
        headers: {
          'X-amz-acl': 'private',
        },
        signal: abortController.signal,
        onProgress: (progress) => {
          setState((current) => ({
            ...current,
            uploadProgress: progress.percent,
          }))
        },
      })

      await chunkStore.clearRecording(recordingId)
      useLocalRecordingsStore.getState().removeRecording(recordingId)
      activeRecordingIdRef.current = null
      setState((current) => ({
        ...current,
        currentRecordingId: null,
      }))

      const apiFile = await markUploadEnded(pendingFile.id)
      queryClient.invalidateQueries({
        queryKey: [keys.files],
      })

      setState((current) => ({
        ...current,
        isUploading: false,
        uploadProgress: 100,
      }))
      accumulatedDurationMsRef.current = 0
      setState((current) => ({
        ...current,
        recordingDurationMs: 0,
      }))
      return apiFile
    } catch (error) {
      const aborted =
        error instanceof DOMException && error.name === 'AbortError'
      useLocalRecordingsStore.getState().updateRecording(recordingId, {
        status: 'stopped',
      })
      setState((current) => ({
        ...current,
        isUploading: false,
        uploadError: aborted
          ? null
          : error instanceof Error
            ? error.message
            : 'Upload failed',
      }))
    }
  }, [queryClient, recoverableRecording?.id, t])

  const downloadCurrentRecording = useCallback(async () => {
    const chunkStore = chunkStoreRef.current
    if (!chunkStore) {
      return
    }

    const recordingId =
      activeRecordingIdRef.current ?? recoverableRecording?.id ?? null
    if (!recordingId) {
      return
    }

    const recording = useLocalRecordingsStore
      .getState()
      .getRecordingById(recordingId)
    if (!recording) {
      return
    }

    const chunks: Blob[] = []
    for await (const chunk of chunkStore.getChunkStream(recordingId)) {
      chunks.push(chunk)
    }

    const filename = `${t('record:recordingPrefix')} ${t('shared:utils.formatDateTimeStatic', { value: recording.createdAt })}.${getExtensionFromMimeType(recording.mimeType)}`
    const file = new File(chunks, filename, {
      type: recording.mimeType || 'audio/webm',
    })

    await chunkStore.clearRecording(recordingId)
    useLocalRecordingsStore.getState().removeRecording(recordingId)
    if (activeRecordingIdRef.current === recordingId) {
      activeRecordingIdRef.current = null
    }
    setState((current) => ({
      ...current,
      currentRecordingId: null,
      uploadError: null,
      uploadProgress: 0,
      isUploading: false,
    }))

    return file
  }, [recoverableRecording?.id, t])

  const clearRecoverableRecording = useCallback(async () => {
    const recordingId = recoverableRecording?.id
    if (!recordingId) {
      return
    }
    await chunkStoreRef.current?.clearRecording(recordingId)
    useLocalRecordingsStore.getState().removeRecording(recordingId)
    setState((current) => ({
      ...current,
      uploadError: null,
      uploadProgress: 0,
    }))
    if (activeRecordingIdRef.current === recordingId) {
      activeRecordingIdRef.current = null
      setState((current) => ({
        ...current,
        currentRecordingId: null,
      }))
    }
  }, [recoverableRecording?.id])

  return useMemo(() => {
    const canPauseOrStop =
      state.recorderState === 'recording' || state.recorderState === 'paused'

    return {
      ...state,
      canPauseOrStop,
      isPaused: state.recorderState === 'paused',
      recoverableRecording,
      hasRecoverableRecording: Boolean(recoverableRecording),
      startRecording,
      pauseRecording,
      resumeRecording,
      stopRecording,
      switchAudioInput,
      uploadCurrentRecording,
      downloadCurrentRecording,
      clearRecoverableRecording,
    }
  }, [
    clearRecoverableRecording,
    pauseRecording,
    recoverableRecording,
    resumeRecording,
    startRecording,
    state,
    stopRecording,
    switchAudioInput,
    uploadCurrentRecording,
    downloadCurrentRecording,
  ])
}
