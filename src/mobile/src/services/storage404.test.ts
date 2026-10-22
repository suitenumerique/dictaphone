import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/ApiError'
import { UploadFinalizationNotFoundError } from '../api/UploadFinalizationNotFoundError'
import { UPLOAD_RETRY_BASE_DELAY_MS as RETRY_DELAY } from './uploadRetry'

const mocks = vi.hoisted(() => ({
  createFile: vi.fn(),
  finalizeFileUpload: vi.fn(),
  getUploadStatuses: vi.fn(),
  clearUpload: vi.fn(),
  deleteLocalRecordingFile: vi.fn(),
  markUploadFinalized: vi.fn(),
  values: new Map<string, string>(),
}))

vi.mock(
  '@/features/ai-jobs/constants',
  () => import('../features/ai-jobs/constants')
)
vi.mock(
  '@/api/UploadFinalizationNotFoundError',
  () => import('../api/UploadFinalizationNotFoundError')
)
vi.mock('@/services/uploadSelection', () => import('./uploadSelection'))
vi.mock('@/api/queryKeys', () => import('../api/queryKeys'))
vi.mock('@/utils/omit', () => import('../utils/omit'))

vi.mock('@/services/index', () => ({
  mmkvStorage: {
    getItem: (key: string) => mocks.values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      mocks.values.set(key, value)
    },
    removeItem: (key: string) => {
      mocks.values.delete(key)
    },
  },
}))
vi.mock('@/services/userStore', () => ({
  useUserStore: {
    getState: () => ({ user: { id: 'user' }, authExpired: false }),
    subscribe: vi.fn(),
  },
}))
vi.mock('@react-native-community/netinfo', () => ({
  default: {
    fetch: async () => ({ isConnected: true, type: 'wifi' }),
    addEventListener: vi.fn(),
  },
}))
vi.mock('react-native', () => ({
  AppState: { currentState: 'active', addEventListener: vi.fn() },
}))
vi.mock('@/features/files/api/createFile', () => ({
  createFile: mocks.createFile,
  finalizeFileUpload: mocks.finalizeFileUpload,
}))
vi.mock('@/utils/fileUpload', () => ({
  clearUpload: mocks.clearUpload,
  getUploadStatuses: mocks.getUploadStatuses,
  markUploadFinalized: mocks.markUploadFinalized,
  requestUploadNotificationPermission: async () => {},
  setFileUploadAppActive: vi.fn(),
}))
vi.mock('@/utils/localRecordingFile', () => ({
  getFileName: (path: string) => path.split('/').pop() ?? path,
  deleteLocalRecordingFile: mocks.deleteLocalRecordingFile,
  listDocumentM4AFiles: async () => [],
  localRecordingFileExists: async () => true,
}))
vi.mock('@/features/recordings/utils/concatSubAudioFiles', () => ({
  FILENAME_PREFIX_SEPARATOR: '__',
}))
vi.mock('@/api/queryClient', () => ({
  queryClient: { invalidateQueries: async () => {} },
}))
vi.mock('@/i18n', () => ({ default: { t: (key: string) => key } }))
vi.mock('@/utils/wait', () => ({ wait: async () => {} }))
vi.mock('react-native-uuid', () => ({ default: { v4: () => 'uuid' } }))

import {
  retryRecordingUpload,
  setBypassWifiOnly,
  useRecordingsStore,
} from './storage'

const recording = {
  id: 'local-recording',
  filePath: '/documents/audio.m4a',
  title: 'Audio',
  language: 'fr' as const,
  duration_seconds: 42,
  created_at: '2026-10-21T10:00:00Z',
  uploadingStatus: 'uploading' as const,
  fileId: 'old-file',
  uploadId: 'old-upload',
}
const currentRecording = () => useRecordingsStore.getState().recordings[0]

describe('bounded upload retries', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    mocks.clearUpload.mockResolvedValue(undefined)
    mocks.getUploadStatuses.mockResolvedValue([
      {
        uploadId: 'old-upload',
        status: 'uploadedAwaitingFinalize',
        uploadedBytes: 100,
        totalBytes: 100,
      },
    ])
    mocks.finalizeFileUpload.mockRejectedValue(
      new UploadFinalizationNotFoundError({})
    )
    mocks.deleteLocalRecordingFile.mockResolvedValue(undefined)
    mocks.createFile.mockImplementation(async (options) => {
      options.onUploadPrepared({
        fileId: 'new-file',
        uploadId: options.uploadId,
      })
      throw new UploadFinalizationNotFoundError({})
    })
    useRecordingsStore.setState({ recordings: [] })
  })
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('bounds repeated finalization 404s to three attempts and retains audio', async () => {
    useRecordingsStore.setState({ recordings: [recording] })
    setBypassWifiOnly(true)
    await vi.advanceTimersByTimeAsync(3 * RETRY_DELAY)
    expect(mocks.clearUpload).toHaveBeenCalledTimes(3)
    expect(mocks.clearUpload).toHaveBeenNthCalledWith(1, 'old-upload')
    expect(mocks.createFile).toHaveBeenCalledTimes(2)
    expect(mocks.createFile).toHaveBeenCalledWith(
      expect.objectContaining({
        file: expect.objectContaining({ uri: recording.filePath }),
      })
    )
    expect(currentRecording()).toMatchObject({
      filePath: recording.filePath,
      uploadingStatus: 'blocked',
      uploadAttemptCount: 3,
      uploadBlockedReason: 'transient',
      fileId: undefined,
      uploadId: undefined,
      uploadProgress: undefined,
    })
    await vi.advanceTimersByTimeAsync(60_000)
    expect(mocks.createFile).toHaveBeenCalledTimes(2)
    expect(mocks.deleteLocalRecordingFile).not.toHaveBeenCalled()
    expect(mocks.markUploadFinalized).not.toHaveBeenCalled()
  })

  it('grants a new budget on explicit Retry upload', async () => {
    useRecordingsStore.setState({
      recordings: [
        {
          ...recording,
          uploadingStatus: 'blocked',
          uploadAttemptCount: 3,
          uploadBlockedReason: 'transient',
        },
      ],
    })
    retryRecordingUpload(recording.id)
    await vi.advanceTimersByTimeAsync(3 * RETRY_DELAY)
    expect(mocks.clearUpload).toHaveBeenCalledTimes(3)
    expect(currentRecording().uploadAttemptCount).toBe(3)
    expect(currentRecording().uploadingStatus).toBe('blocked')
  })

  it('unblocks exhausted transient failures after restart', async () => {
    useRecordingsStore.setState({
      recordings: [
        {
          ...recording,
          uploadingStatus: 'blocked',
          uploadAttemptCount: 3,
          uploadBlockedReason: 'transient',
        },
      ],
    })
    await useRecordingsStore.persist.rehydrate()
    expect(currentRecording().uploadAttemptCount).toBe(0)
    expect(currentRecording().uploadingStatus).toBe('uploading')
    expect(currentRecording().uploadBlockedReason).toBeUndefined()
  })

  it('recovers an initial upload and deletes audio only after success', async () => {
    mocks.createFile
      .mockImplementationOnce(async (options) => {
        options.onUploadPrepared({
          fileId: 'first-file',
          uploadId: options.uploadId,
        })
        throw new UploadFinalizationNotFoundError({})
      })
      .mockResolvedValueOnce({ id: 'successful-file' })
    useRecordingsStore.setState({
      recordings: [
        {
          ...recording,
          fileId: undefined,
          uploadId: undefined,
          uploadingStatus: 'to_upload',
        },
      ],
    })
    setBypassWifiOnly(true)
    await vi.advanceTimersByTimeAsync(RETRY_DELAY)
    expect(useRecordingsStore.getState().recordings).toEqual([])
    expect(mocks.createFile).toHaveBeenCalledTimes(2)
    expect(mocks.clearUpload).toHaveBeenCalledTimes(1)
    expect(mocks.deleteLocalRecordingFile).toHaveBeenCalledWith(
      recording.filePath
    )
  })

  it('retries transient finalization failures with backoff using the same backend ID', async () => {
    mocks.finalizeFileUpload.mockRejectedValue(new ApiError(500, {}))
    useRecordingsStore.setState({ recordings: [recording] })
    setBypassWifiOnly(true)
    await vi.advanceTimersByTimeAsync(0)
    expect(mocks.finalizeFileUpload).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(RETRY_DELAY - 1)
    expect(mocks.finalizeFileUpload).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(mocks.finalizeFileUpload).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(2 * RETRY_DELAY)
    expect(mocks.finalizeFileUpload).toHaveBeenCalledTimes(3)
    expect(mocks.finalizeFileUpload.mock.calls).toEqual([
      ['old-file'],
      ['old-file'],
      ['old-file'],
    ])
    expect(mocks.clearUpload).not.toHaveBeenCalled()
    expect(mocks.createFile).not.toHaveBeenCalled()
    expect(currentRecording().fileId).toBe('old-file')
    expect(currentRecording().uploadingStatus).toBe('blocked')
  })

  it('shares the budget between transient errors and missing backend files', async () => {
    mocks.finalizeFileUpload.mockRejectedValueOnce(new ApiError(500, {}))
    useRecordingsStore.setState({ recordings: [recording] })
    setBypassWifiOnly(true)
    await vi.advanceTimersByTimeAsync(3 * RETRY_DELAY)
    expect(mocks.finalizeFileUpload).toHaveBeenCalledTimes(2)
    expect(mocks.createFile).toHaveBeenCalledTimes(1)
    expect(currentRecording().uploadingStatus).toBe('blocked')
    expect(currentRecording().uploadAttemptCount).toBe(3)
  })

  it('retries a new upload finalization without retransferring its completed audio', async () => {
    mocks.createFile.mockImplementationOnce(async (options) => {
      options.onUploadPrepared({
        fileId: 'new-file',
        uploadId: options.uploadId,
      })
      mocks.getUploadStatuses.mockResolvedValue([
        {
          uploadId: options.uploadId,
          status: 'uploadedAwaitingFinalize',
          uploadedBytes: 100,
          totalBytes: 100,
        },
      ])
      throw new ApiError(500, {})
    })
    mocks.finalizeFileUpload.mockRejectedValue(new ApiError(500, {}))
    useRecordingsStore.setState({
      recordings: [
        {
          ...recording,
          fileId: undefined,
          uploadId: undefined,
          uploadingStatus: 'to_upload',
        },
      ],
    })
    setBypassWifiOnly(true)
    await vi.advanceTimersByTimeAsync(3 * RETRY_DELAY)
    expect(mocks.createFile).toHaveBeenCalledOnce()
    expect(mocks.finalizeFileUpload.mock.calls).toEqual([
      ['new-file'],
      ['new-file'],
    ])
    expect(currentRecording().uploadingStatus).toBe('blocked')
    expect(mocks.clearUpload).not.toHaveBeenCalled()
  })

  it('bounds network failures before file creation completes', async () => {
    mocks.createFile.mockRejectedValue(new TypeError('Network request failed'))
    useRecordingsStore.setState({
      recordings: [
        {
          ...recording,
          fileId: undefined,
          uploadId: undefined,
          uploadingStatus: 'to_upload',
        },
      ],
    })
    setBypassWifiOnly(true)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(mocks.createFile).toHaveBeenCalledTimes(3)
    expect(currentRecording().uploadingStatus).toBe('blocked')
    expect(mocks.deleteLocalRecordingFile).not.toHaveBeenCalled()
  })

  it('uploads other recordings while one waits for its retry', async () => {
    mocks.finalizeFileUpload.mockRejectedValue(new ApiError(500, {}))
    mocks.createFile.mockResolvedValue({ id: 'other-file' })
    useRecordingsStore.setState({
      recordings: [
        recording,
        {
          ...recording,
          id: 'other',
          fileId: undefined,
          uploadId: undefined,
          uploadingStatus: 'to_upload',
        },
      ],
    })
    setBypassWifiOnly(true)
    await vi.advanceTimersByTimeAsync(0)
    expect(mocks.createFile).toHaveBeenCalledOnce()
    expect(useRecordingsStore.getState().recordings).toHaveLength(1)
    expect(currentRecording().id).toBe(recording.id)
    expect(currentRecording().uploadAttemptCount).toBe(1)
    expect(mocks.finalizeFileUpload).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(3 * RETRY_DELAY)
    expect(currentRecording().uploadingStatus).toBe('blocked')
  })

  it('does not charge 429 responses against the retry budget', async () => {
    mocks.finalizeFileUpload.mockRejectedValue(new ApiError(429, {}))
    useRecordingsStore.setState({
      recordings: [{ ...recording, uploadAttemptCount: 2 }],
    })
    setBypassWifiOnly(true)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(mocks.finalizeFileUpload).toHaveBeenCalledOnce()
    expect(currentRecording().uploadAttemptCount).toBe(2)
    expect(currentRecording()).toMatchObject({
      uploadingStatus: 'to_upload',
      fileId: 'old-file',
      uploadId: 'old-upload',
    })
    expect(mocks.clearUpload).not.toHaveBeenCalled()
  })

  it.each([400, 401, 403, 404])(
    'blocks HTTP %s immediately and keeps it blocked across restart',
    async (status) => {
      mocks.finalizeFileUpload.mockRejectedValue(new ApiError(status, {}))
      useRecordingsStore.setState({ recordings: [recording] })
      setBypassWifiOnly(true)
      await vi.advanceTimersByTimeAsync(60_000)
      expect(currentRecording().uploadingStatus).toBe('blocked')
      expect(mocks.finalizeFileUpload).toHaveBeenCalledTimes(1)
      expect(mocks.clearUpload).not.toHaveBeenCalled()
      expect(mocks.createFile).not.toHaveBeenCalled()
      await useRecordingsStore.persist.rehydrate()
      expect(currentRecording().uploadingStatus).toBe('blocked')
    }
  )

  it('starts over with a new backend file even when native cleanup fails', async () => {
    mocks.clearUpload.mockRejectedValue(new Error('Native cleanup failed'))
    mocks.createFile.mockResolvedValue({ id: 'new-file' })
    useRecordingsStore.setState({ recordings: [recording] })
    setBypassWifiOnly(true)
    await vi.advanceTimersByTimeAsync(RETRY_DELAY)
    expect(mocks.clearUpload).toHaveBeenCalledExactlyOnceWith('old-upload')
    expect(mocks.createFile).toHaveBeenCalledOnce()
    expect(useRecordingsStore.getState().recordings).toEqual([])
  })
})
