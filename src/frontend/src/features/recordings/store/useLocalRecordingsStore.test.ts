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
    clearRateLimit('upload')
    resumeLocalUploads()
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
    useLocalRecordingsStore.getState().upsertRecording({ ...recording })
    await useLocalRecordingsStore.persist.rehydrate()
    expect(
      useLocalRecordingsStore.getState().getRecordingById('local')
    ).toMatchObject({ status: 'upload_failed', language: 'fr' })
  })
})
