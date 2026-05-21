import { keys } from '@/api/queryKeys.ts'
import { queryClient } from '@/api/queryClient.ts'
import {
  createPendingAudioFile,
  markUploadEnded,
} from '@/features/files/api/createFile.ts'
import {
  IndexedDbChunkStore,
  UploadStreamManager,
} from '@/features/recordings/recorder'
import { StoredRecording } from '@/features/recordings/recorder/types.ts'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { IDBPDatabase } from 'idb'
import { RecorderDatabaseSchema } from '@/features/recordings/recorder/IndexedDbChunkStore'

const chunkStore = new IndexedDbChunkStore()
const uploadManager = new UploadStreamManager(chunkStore)

let storageReadyPromise: Promise<IDBPDatabase<RecorderDatabaseSchema>> | null =
  null

const ensureStorageReady = () => {
  if (!storageReadyPromise) {
    storageReadyPromise = chunkStore.openDatabase().catch((error) => {
      storageReadyPromise = null
      throw error
    })
  }
  return storageReadyPromise
}

const uploadRecording = async (recordingId: string) => {
  const storeState = useLocalRecordingsStore.getState()
  const recording = storeState.getRecordingById(recordingId)
  if (!recording) return
  if (recording.chunkCount <= 0) {
    storeState.removeRecording(recordingId)
    return
  }

  storeState.updateRecording(recordingId, {
    status: 'uploading',
    uploadProgress: 0,
    uploadError: null,
  })

  try {
    await ensureStorageReady()

    const pendingFile = await createPendingAudioFile({
      filename: recording.filename,
      durationSeconds: Math.max(0, recording.durationMs / 1000),
      createdAt: new Date(recording.createdAt).toISOString(),
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
      onProgress: (progress) => {
        useLocalRecordingsStore.getState().updateRecording(recordingId, {
          status: 'uploading',
          uploadProgress: progress.percent,
          uploadError: null,
        })
      },
    })
    await markUploadEnded(pendingFile.id)

    await chunkStore.clearRecording(recordingId)
    useLocalRecordingsStore.getState().removeRecording(recordingId)
    queryClient.invalidateQueries({
      queryKey: [keys.files],
    })
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === 'AbortError'
    useLocalRecordingsStore.getState().updateRecording(recordingId, {
      status: aborted ? 'stopped' : 'upload_failed',
      uploadError: aborted || !(error instanceof Error) ? null : error.message,
    })
  }
}

export const createLocalFileFromChunkStore = async (
  recordingId: string
): Promise<File> => {
  await ensureStorageReady()

  const recording = useLocalRecordingsStore
    .getState()
    .getRecordingById(recordingId)
  if (!recording) {
    throw new Error('Recording not found')
  }

  const chunks: Blob[] = []
  for await (const chunk of chunkStore.getChunkStream(recordingId)) {
    chunks.push(chunk)
  }

  return new File(chunks, recording.filename, {
    type: recording.mimeType || 'audio/webm',
  })
}

type LocalRecordingsState = {
  recordingsById: Record<string, StoredRecording>
  upsertRecording: (recording: StoredRecording) => void
  updateRecording: (
    recordingId: string,
    patch: Partial<Omit<StoredRecording, 'id' | 'createdAt'>>
  ) => void
  removeRecording: (recordingId: string) => void
  getRecordingById: (recordingId: string) => StoredRecording | null
  getAllRecordings: () => StoredRecording[]
  requestUpload: (recordingId: string) => Promise<void>
}

export const useLocalRecordingsStore = create<LocalRecordingsState>()(
  persist(
    (set, get) => ({
      recordingsById: {},
      upsertRecording: (recording) =>
        set((state) => ({
          recordingsById: {
            ...state.recordingsById,
            [recording.id]: recording,
          },
        })),
      updateRecording: (recordingId, patch) =>
        set((state) => {
          const current = state.recordingsById[recordingId]
          if (!current) {
            return state
          }
          return {
            recordingsById: {
              ...state.recordingsById,
              [recordingId]: {
                ...current,
                ...patch,
                updatedAt: Date.now(),
              },
            },
          }
        }),
      removeRecording: (recordingId) =>
        set((state) => {
          if (!state.recordingsById[recordingId]) {
            return state
          }
          const next = { ...state.recordingsById }
          delete next[recordingId]
          void chunkStore.clearRecording(recordingId)
          return { recordingsById: next }
        }),
      getRecordingById: (recordingId) =>
        get().recordingsById[recordingId] ?? null,
      getAllRecordings: () => Object.values(get().recordingsById),
      requestUpload: async (recordingId) => {
        const recording = get().recordingsById[recordingId]
        if (
          !recording ||
          recording.chunkCount <= 0 ||
          recording.status === 'recording' ||
          recording.status === 'paused'
        ) {
          return
        }
        get().updateRecording(recordingId, {
          status: 'stopped',
          uploadError: null,
          uploadProgress: 0,
        })
      },
    }),
    {
      name: 'local-recordings-metadata-v1',
      partialize: (state) => ({
        recordingsById: state.recordingsById,
      }),
      onRehydrateStorage: () => (state, error) => {
        if (error || !state) return

        state.recordingsById = Object.fromEntries(
          Object.entries(state.recordingsById).map(([id, recording]) => [
            id,
            {
              ...recording,
              status:
                recording.status === 'recording' ||
                recording.status === 'uploading' ||
                recording.status === 'paused'
                  ? 'exited'
                  : recording.status,
            },
          ])
        )
      },
    }
  )
)

function checkUploads() {
  const recordings = Object.values(
    useLocalRecordingsStore.getState().recordingsById
  )
  const isUploading = recordings.some((r) => r.status === 'uploading')
  if (!isUploading) {
    const nextUpload = recordings.find((r) => r.status === 'stopped')
    if (nextUpload) {
      void uploadRecording(nextUpload.id)
    }
  }
}

useLocalRecordingsStore.subscribe((newState, prevState) => {
  if (newState.recordingsById !== prevState?.recordingsById) {
    checkUploads()
  }
})
