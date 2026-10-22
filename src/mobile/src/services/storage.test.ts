import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { create } from 'zustand'
import type { LocalRecording } from '../types/localRecording'
import { ApiError } from '../api/ApiError'
import {
  areUploadsPaused,
  clearRateLimits,
  recordRateLimit,
} from '../api/rateLimits'

const mocks = vi.hoisted(() => ({
  createFile: vi.fn(),
  finalizeFileUpload: vi.fn(),
  getUploadStatuses: vi.fn(),
  markUploadFinalized: vi.fn(),
  nativeEvents: [] as (() => void)[],
  storage: new Map<string, string>(),
}))

vi.mock('react-native', () => ({
  AppState: { currentState: 'active', addEventListener: vi.fn() },
}))
vi.mock('@react-native-community/netinfo', () => ({
  default: {
    fetch: async () => ({ isConnected: true, type: 'wifi' }),
    addEventListener: (listener: () => void) => {
      mocks.nativeEvents.push(listener)
      return () => {}
    },
  },
}))
vi.mock('@/features/files/api/createFile', () => ({
  createFile: mocks.createFile,
  finalizeFileUpload: mocks.finalizeFileUpload,
}))
vi.mock('@/api/queryClient', () => ({
  queryClient: { invalidateQueries: vi.fn() },
}))
vi.mock('@/services/index', () => ({
  mmkvStorage: {
    getItem: (key: string) => mocks.storage.get(key) ?? null,
    setItem: (key: string, value: string) => mocks.storage.set(key, value),
    removeItem: (key: string) => mocks.storage.delete(key),
  },
}))
vi.mock('@/services/userStore', () => ({
  useUserStore: create(() => ({ user: { id: 'user' }, authExpired: false })),
}))
vi.mock('@/utils/localRecordingFile', () => ({
  deleteLocalRecordingFile: vi.fn().mockResolvedValue(undefined),
  localRecordingFileExists: async () => true,
  listDocumentM4AFiles: async () => [],
  getFileName: (name: string) => name,
}))
vi.mock('@/i18n', () => ({ default: { t: (key: string) => key } }))
vi.mock('@/features/recordings/utils/concatSubAudioFiles', () => ({
  concatSubAudioFiles: vi.fn(),
  FILENAME_PREFIX_SEPARATOR: '-',
}))
vi.mock('react-native-uuid', () => ({ default: { v4: () => 'id' } }))
vi.mock('@/utils/fileUpload', () => ({
  getUploadStatuses: mocks.getUploadStatuses,
  markUploadFinalized: mocks.markUploadFinalized,
  clearUpload: vi.fn(),
  resumeUpload: vi.fn(),
  waitForUpload: vi.fn(),
  requestUploadNotificationPermission: vi.fn(),
  setFileUploadAppActive: vi.fn(),
}))

import {
  resumeRateLimitedUploads,
  startRecordingsUploadManager,
  useRecordingsStore,
} from './storage'

const recording = (id: string): LocalRecording => ({
  id,
  title: id,
  filePath: `/${id}.m4a`,
  created_at: '2026-10-19T12:00:00Z',
  duration_seconds: 10,
  uploadingStatus: 'to_upload',
  language: 'fr',
})

const throttle = () => {
  recordRateLimit('upload', Date.now() + 60_000)
  return new ApiError(429, {}, Date.now() + 60_000)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  clearRateLimits()
  useRecordingsStore.setState({
    recordings: [],
    hasHydrated: true,
    recoverFilesStatus: { status: 'done', recovered: [] },
  })
  mocks.getUploadStatuses.mockResolvedValue([])
  mocks.markUploadFinalized.mockResolvedValue(undefined)
})
afterEach(() => vi.restoreAllMocks())

describe('rate-limited uploads', () => {
  it('pauses the queue and resumes finalization without retransferring', async () => {
    startRecordingsUploadManager()
    mocks.createFile.mockImplementationOnce(
      async ({ onUploadPrepared, uploadId }) => {
        onUploadPrepared({ fileId: 'server-file', uploadId })
        // The native module keeps this checkpoint across app restarts.
        mocks.getUploadStatuses.mockResolvedValue([
          {
            uploadId,
            status: 'uploadedAwaitingFinalize',
            uploadedBytes: 10,
            totalBytes: 10,
          },
        ])
        throw throttle()
      }
    )
    useRecordingsStore.getState().addRecording(recording('first'))
    await vi.waitFor(() => expect(areUploadsPaused()).toBe(true))
    await vi.waitFor(() =>
      expect(useRecordingsStore.getState().recordings[0]).toMatchObject({
        fileId: 'server-file',
        uploadingStatus: 'to_upload',
      })
    )

    useRecordingsStore.getState().addRecording(recording('second'))
    for (const listener of mocks.nativeEvents) listener()
    await new Promise((resolve) => setTimeout(resolve, 10))
    expect(mocks.createFile).toHaveBeenCalledTimes(1)
    expect(mocks.finalizeFileUpload).not.toHaveBeenCalled()

    mocks.finalizeFileUpload.mockResolvedValue({ id: 'server-file' })
    mocks.createFile.mockResolvedValue({ id: 'second-file' })
    resumeRateLimitedUploads()
    await vi.waitFor(() =>
      expect(useRecordingsStore.getState().recordings).toEqual([])
    )
    expect(mocks.finalizeFileUpload).toHaveBeenCalledExactlyOnceWith(
      'server-file'
    )
    expect(mocks.createFile).toHaveBeenCalledTimes(2)
  })

  it('keeps audio queued locally when file creation is throttled', async () => {
    startRecordingsUploadManager()
    mocks.createFile.mockImplementationOnce(async () => {
      throw throttle()
    })
    useRecordingsStore.getState().addRecording(recording('creation'))
    await vi.waitFor(() => expect(areUploadsPaused()).toBe(true))
    await vi.waitFor(() =>
      expect(useRecordingsStore.getState().recordings[0].uploadingStatus).toBe(
        'to_upload'
      )
    )
    expect(useRecordingsStore.getState().recordings[0].fileId).toBeUndefined()
    expect(mocks.finalizeFileUpload).not.toHaveBeenCalled()

    mocks.createFile.mockResolvedValue({ id: 'created' })
    resumeRateLimitedUploads()
    await vi.waitFor(() =>
      expect(useRecordingsStore.getState().recordings).toEqual([])
    )
  })
})

describe('rate-limit auto resume', () => {
  it('resumes uploads by itself once Retry-After expires', async () => {
    startRecordingsUploadManager()
    mocks.createFile.mockImplementationOnce(async () => {
      recordRateLimit('upload', Date.now() + 50)
      throw new ApiError(429, {}, Date.now() + 50)
    })
    mocks.createFile.mockResolvedValue({ id: 'created' })
    useRecordingsStore.getState().addRecording(recording('auto'))
    await vi.waitFor(() => expect(areUploadsPaused()).toBe(true))
    await vi.waitFor(() =>
      expect(useRecordingsStore.getState().recordings).toEqual([])
    )
    expect(areUploadsPaused()).toBe(false)
    expect(mocks.createFile).toHaveBeenCalledTimes(2)
  })

  it('waits for the user when the server gives no Retry-After', async () => {
    startRecordingsUploadManager()
    recordRateLimit('upload', null)
    useRecordingsStore.getState().addRecording(recording('manual'))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(areUploadsPaused()).toBe(true)
    expect(mocks.createFile).not.toHaveBeenCalled()
  })
})
