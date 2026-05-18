import { StoredRecording } from '@/features/recordings/recorder/types.ts'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type LocalRecordingsState = {
  recordingsById: Record<string, StoredRecording>
  upsertRecording: (recording: StoredRecording) => void
  updateRecording: (
    recordingId: string,
    patch: Partial<Omit<StoredRecording, 'id' | 'createdAt'>>
  ) => void
  removeRecording: (recordingId: string) => void
  removeManyRecordings: (recordingIds: string[]) => void
  getRecordingById: (recordingId: string) => StoredRecording | null
  getAllRecordings: () => StoredRecording[]
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
          return { recordingsById: next }
        }),
      removeManyRecordings: (recordingIds) =>
        set((state) => {
          if (recordingIds.length === 0) {
            return state
          }
          const next = { ...state.recordingsById }
          for (const recordingId of recordingIds) {
            delete next[recordingId]
          }
          return { recordingsById: next }
        }),
      getRecordingById: (recordingId) =>
        get().recordingsById[recordingId] ?? null,
      getAllRecordings: () => Object.values(get().recordingsById),
    }),
    {
      name: 'local-recordings-metadata-v1',
      partialize: (state) => ({
        recordingsById: state.recordingsById,
      }),
    }
  )
)

const RECOVERABLE_STATES = new Set([
  'recording',
  'paused',
  'stopped',
  'uploading',
])

export const selectLatestRecoverableRecording = (state: LocalRecordingsState) =>
  Object.values(state.recordingsById)
    .filter(
      (recording) =>
        RECOVERABLE_STATES.has(recording.status) && recording.chunkCount > 0
    )
    .sort((a, b) => b.updatedAt - a.updatedAt)[0] ?? null
