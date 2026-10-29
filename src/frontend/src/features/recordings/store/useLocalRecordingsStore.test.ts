import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/ApiError'
import {
  clearRateLimit,
  clearRateLimits,
  recordRateLimit,
} from '@/api/rateLimits'
import {
  createPendingAudioFile,
  markUploadEnded,
} from '@/features/files/api/createFile'
import type { StoredRecording } from '../recorder/types'

const mocks = vi.hoisted(() => {
  const values = new Map<string, string>()
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value)
    },
    removeItem: (key: string) => {
      values.delete(key)
    },
  }
  return {
    storage,
    upload: vi.fn().mockResolvedValue(undefined),
    clear: vi.fn().mockResolvedValue(undefined),
  }
})
vi.mock('zustand/middleware', async (importOriginal) => {
  const actual = await importOriginal<typeof import('zustand/middleware')>()
  return {
    ...actual,
    persist: ((...args: Parameters<typeof actual.persist>) =>
      actual.persist(args[0], {
        ...args[1],
        storage: actual.createJSONStorage<unknown>(() => mocks.storage),
      })) as typeof actual.persist,
  }
})
vi.mock('@/features/recordings/recorder', () => ({
  IndexedDbChunkStore: class {
    openDatabase = () => Promise.resolve({})
    clearRecording = mocks.clear
  },
  UploadStreamManager: class {
    uploadRecording = mocks.upload
    isUploading = () => false
  },
}))
vi.mock('@/features/files/api/createFile', () => ({
  createPendingAudioFile: vi.fn(),
  markUploadEnded: vi.fn(),
}))
vi.mock('@/api/queryClient', () => ({
  queryClient: { invalidateQueries: vi.fn() },
}))

const { resumeLocalUploads, useLocalRecordingsStore } =
  await import('./useLocalRecordingsStore')

const recording: StoredRecording = {
  id: 'local',
  createdAt: 1,
  updatedAt: 1,
  filename: 'recording.webm',
  mimeType: 'audio/webm',
  status: 'upload_failed',
  chunkCount: 1,
  totalBytes: 10,
  durationMs: 10_000,
  uploadProgress: 0,
  uploadError: null,
  source: 'web_recording',
  language: 'fr',
}

beforeEach(() => {
  clearRateLimits()
  useLocalRecordingsStore.setState({ recordingsById: {} })
  vi.clearAllMocks()
  vi.mocked(createPendingAudioFile).mockResolvedValue({
    id: 'server',
    policy: '/storage',
    acl: null,
  } as Awaited<ReturnType<typeof createPendingAudioFile>>)
})

const getStatus = (id: string) =>
  useLocalRecordingsStore.getState().getRecordingById(id)?.status

const throttle = async () => {
  recordRateLimit('upload', Date.now() + 60_000)
  throw new ApiError(429, {}, Date.now() + 60_000)
}

describe('local recording recovery', () => {
  it('pauses the remaining local queue on file creation throttling and resumes it manually', async () => {
    vi.mocked(createPendingAudioFile).mockImplementationOnce(throttle)
    vi.mocked(markUploadEnded).mockResolvedValue(
      {} as Awaited<ReturnType<typeof markUploadEnded>>
    )
    useLocalRecordingsStore.getState().upsertRecording({ ...recording })
    await useLocalRecordingsStore.getState().requestUpload('local')
    useLocalRecordingsStore
      .getState()
      .upsertRecording({ ...recording, id: 'second', status: 'stopped' })
    await vi.waitFor(() =>
      expect(createPendingAudioFile).toHaveBeenCalledTimes(1)
    )
    await vi.waitFor(() => expect(getStatus('local')).toBe('stopped'))
    expect(mocks.upload).not.toHaveBeenCalled()
    expect(getStatus('second')).toBe('stopped')
    // An expired cooldown still waits for the user to resume uploads.
    recordRateLimit('upload', 0)
    await useLocalRecordingsStore.getState().requestUpload('local')
    expect(createPendingAudioFile).toHaveBeenCalledTimes(1)
    clearRateLimit('upload')
    resumeLocalUploads()
    await vi.waitFor(() =>
      expect(
        useLocalRecordingsStore.getState().getAllRecordings()
      ).toHaveLength(0)
    )
    expect(createPendingAudioFile).toHaveBeenCalledTimes(3)
    expect(markUploadEnded).toHaveBeenCalledTimes(2)
  })

  it('retains audio and the finalization checkpoint through reload, then resumes only finalization', async () => {
    vi.mocked(markUploadEnded)
      .mockImplementationOnce(throttle)
      .mockResolvedValue({} as Awaited<ReturnType<typeof markUploadEnded>>)
    useLocalRecordingsStore.getState().upsertRecording({ ...recording })
    await useLocalRecordingsStore.getState().requestUpload('local')
    await vi.waitFor(() => expect(markUploadEnded).toHaveBeenCalledTimes(1))
    await vi.waitFor(() => expect(getStatus('local')).toBe('stopped'))
    expect(mocks.clear).not.toHaveBeenCalled()
    expect(
      useLocalRecordingsStore.getState().getRecordingById('local')
        ?.finalizationFileId
    ).toBe('server')
    await useLocalRecordingsStore.persist.rehydrate()
    expect(getStatus('local')).toBe('exited')
    clearRateLimit('upload')
    await useLocalRecordingsStore.getState().requestUpload('local')
    await vi.waitFor(() =>
      expect(
        useLocalRecordingsStore.getState().getRecordingById('local')
      ).toBeNull()
    )
    expect(createPendingAudioFile).toHaveBeenCalledTimes(1)
    expect(mocks.upload).toHaveBeenCalledTimes(1)
    expect(markUploadEnded).toHaveBeenCalledTimes(2)
  })
  it('recovers old stored metadata without the new optional fields', async () => {
    const { language: _language, ...legacyRecording } = recording
    mocks.storage.setItem(
      'local-recordings-metadata-v1',
      JSON.stringify({ state: { recordingsById: { local: legacyRecording } } })
    )
    await useLocalRecordingsStore.persist.rehydrate()
    expect(
      useLocalRecordingsStore.getState().getRecordingById('local')
    ).toMatchObject({ status: 'upload_failed', language: 'fr' })
  })

  it.each(
    (['recording', 'paused', 'uploading', 'stopped'] as const).flatMap(
      (status) => [
        { status, finalizationFileId: undefined },
        { status, finalizationFileId: 'server' },
      ]
    )
  )(
    'recovers $status with checkpoint $finalizationFileId on initial hydration and allows retry',
    async ({ status, finalizationFileId }) => {
      mocks.storage.setItem(
        'local-recordings-metadata-v1',
        JSON.stringify({
          state: {
            recordingsById: {
              local: {
                ...recording,
                status,
                finalizationFileId,
                uploadProgress: 43,
                uploadError: 'previous upload error',
              },
              empty: { ...recording, id: 'empty', status, chunkCount: 0 },
            },
          },
        })
      )

      // Import a fresh store: rehydrate() alone misses initialization-order bugs.
      vi.resetModules()
      const { useLocalRecordingsStore: store } =
        await import('./useLocalRecordingsStore')
      const api = await import('@/features/files/api/createFile')
      vi.mocked(api.createPendingAudioFile).mockResolvedValue({
        id: 'server',
        policy: '/storage',
        acl: null,
      } as Awaited<ReturnType<typeof createPendingAudioFile>>)
      vi.mocked(api.markUploadEnded).mockResolvedValue(
        {} as Awaited<ReturnType<typeof markUploadEnded>>
      )

      expect(store.persist.hasHydrated()).toBe(true)
      expect(store.getState().getAllRecordings()).toHaveLength(1)
      expect(store.getState().getRecordingById('local')).toMatchObject({
        status: 'exited',
        uploadProgress: finalizationFileId ? 100 : 0,
        uploadError: null,
        chunkCount: 1,
        totalBytes: 10,
      })
      expect(
        store.getState().getRecordingById('local')?.finalizationFileId
      ).toBe(finalizationFileId)
      expect(api.createPendingAudioFile).not.toHaveBeenCalled()
      expect(mocks.clear).not.toHaveBeenCalled()

      await store.getState().requestUpload('local')
      await vi.waitFor(() =>
        expect(store.getState().getAllRecordings()).toEqual([])
      )
      expect(api.createPendingAudioFile).toHaveBeenCalledTimes(
        finalizationFileId ? 0 : 1
      )
      expect(mocks.upload).toHaveBeenCalledTimes(finalizationFileId ? 0 : 1)
      expect(api.markUploadEnded).toHaveBeenCalledWith('server')
    }
  )
})
