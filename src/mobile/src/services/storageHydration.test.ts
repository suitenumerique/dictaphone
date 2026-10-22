import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  createFile: vi.fn(),
  finalizeFileUpload: vi.fn(),
  getUploadStatuses: vi.fn(),
  clearUpload: vi.fn(),
  deleteLocalRecordingFile: vi.fn(),
  markUploadFinalized: vi.fn(),
  values: new Map<string, string>(),
  localRecordingFileExists: vi.fn(),
  readError: false,
}))

vi.mock('@/services/index', () => ({
  mmkvStorage: {
    getItem: (key: string) => {
      if (mocks.readError) throw new Error('Storage unavailable')
      return mocks.values.get(key) ?? null
    },
    setItem: (key: string, value: string) => {
      mocks.values.set(key, value)
    },
    removeItem: (key: string) => {
      mocks.values.delete(key)
    },
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
  localRecordingFileExists: mocks.localRecordingFileExists,
}))
vi.mock('@/features/recordings/utils/concatSubAudioFiles', () => ({
  FILENAME_PREFIX_SEPARATOR: '__',
}))
vi.mock('@/api/queryClient', () => ({
  queryClient: { invalidateQueries: async () => {} },
}))
vi.mock('@/i18n', () => ({
  default: { language: 'fr', changeLanguage: vi.fn(), t: (key: string) => key },
}))
vi.mock('@/utils/wait', () => ({ wait: async () => {} }))
vi.mock('react-native-uuid', () => ({ default: { v4: () => 'uuid' } }))

const recording = {
  id: 'local-recording',
  filePath: '/documents/audio.m4a',
  title: 'Audio',
  language: 'fr',
  duration_seconds: 42,
  created_at: '2026-10-21T10:00:00Z',
  uploadingStatus: 'blocked',
  uploadAttemptCount: 3,
  uploadBlockedReason: 'transient',
  fileId: 'old-file',
  uploadId: 'old-upload',
}

describe('synchronous store initialization', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
    mocks.values.clear()
    mocks.readError = false
    mocks.localRecordingFileExists.mockResolvedValue(true)
  })

  it('finishes hydration with empty storage', async () => {
    const { useRecordingsStore } = await import('./storage')
    expect(useRecordingsStore.getState().hasHydrated).toBe(true)
    expect(useRecordingsStore.persist.hasHydrated()).toBe(true)
    expect(useRecordingsStore.getState().recordings).toEqual([])
  })

  it('normalizes persisted recordings and checks their files during initial hydration', async () => {
    mocks.values.set(
      'recordings',
      JSON.stringify({ version: 1, state: { recordings: [recording] } })
    )
    const { useRecordingsStore } = await import('./storage')
    expect(useRecordingsStore.persist.hasHydrated()).toBe(true)
    expect(useRecordingsStore.getState()).toMatchObject({
      hasHydrated: true,
      recoverFilesStatus: { status: 'to_run' },
      recordings: [
        {
          ...recording,
          uploadingStatus: 'uploading',
          uploadAttemptCount: 0,
          uploadBlockedReason: undefined,
        },
      ],
    })
    expect(mocks.localRecordingFileExists).toHaveBeenCalledExactlyOnceWith(
      recording.filePath
    )
  })

  it('loads and rewrites the existing version-1 format without losing recording metadata', async () => {
    // Older entries predate the optional language, upload and retry fields.
    const legacyRecording = {
      id: 'legacy-recording',
      filePath: '/documents/legacy.m4a',
      title: 'Old recording',
      duration_seconds: 120,
      created_at: '2025-01-01T10:00:00Z',
      uploadingStatus: 'failed',
    }
    const importedRecording = {
      ...recording,
      source: 'mobile_file_upload',
      fileName: 'Original filename.mp3',
      mimeType: 'audio/mpeg',
      uploadBlockedReason: 'permission',
      uploadProgress: {
        uploadedBytes: 50,
        totalBytes: 100,
        progress: 0.5,
        percentage: 50,
      },
    }
    const saved = JSON.stringify({
      state: { recordings: [legacyRecording, importedRecording] },
      version: 1,
    })
    mocks.values.set('recordings', saved)

    const { useRecordingsStore } = await import('./storage')
    const expectedRecordings = [
      {
        ...legacyRecording,
        language: 'fr',
        uploadingStatus: 'to_upload',
        uploadAttemptCount: 0,
      },
      {
        ...importedRecording,
        uploadProgress: undefined,
      },
    ]
    expect(useRecordingsStore.getState().recordings).toMatchObject(
      expectedRecordings
    )
    expect(mocks.values.get('recordings')).toBe(saved)

    // A normal edit must still write the same Zustand envelope and field names.
    useRecordingsStore.getState().updateRecording(legacyRecording.id, {
      title: 'Renamed recording',
    })
    expectedRecordings[0].title = 'Renamed recording'
    expect(JSON.parse(mocks.values.get('recordings')!)).toEqual(
      JSON.parse(
        JSON.stringify({
          state: { recordings: expectedRecordings },
          version: 1,
        })
      )
    )

    vi.resetModules()
    const restarted = await import('./storage')
    expect(restarted.useRecordingsStore.getState().recordings).toEqual(
      useRecordingsStore.getState().recordings
    )
    expect(mocks.deleteLocalRecordingFile).not.toHaveBeenCalled()
  })

  it('removes missing files after initial hydration', async () => {
    mocks.values.set(
      'recordings',
      JSON.stringify({ version: 1, state: { recordings: [recording] } })
    )
    mocks.localRecordingFileExists.mockResolvedValue(false)
    const { useRecordingsStore } = await import('./storage')
    await vi.waitFor(() => {
      expect(useRecordingsStore.getState().recordings).toEqual([])
      expect(useRecordingsStore.getState().missingFilesPending).toBe('• Audio')
    })
    expect(useRecordingsStore.persist.hasHydrated()).toBe(true)
  })

  it('discards invalid persisted recordings', async () => {
    mocks.values.set(
      'recordings',
      JSON.stringify({ version: 1, state: { recordings: [{ id: 'invalid' }] } })
    )
    const { useRecordingsStore } = await import('./storage')
    expect(useRecordingsStore.getState().hasHydrated).toBe(true)
    expect(useRecordingsStore.persist.hasHydrated()).toBe(true)
    expect(useRecordingsStore.getState().recordings).toEqual([])
  })

  it.each(['invalid JSON', 'read failure'])(
    'releases all hydration gates after %s during construction',
    async (failure) => {
      for (const key of ['recordings', 'settings', 'user-info', 'config']) {
        mocks.values.set(
          key,
          failure === 'invalid JSON'
            ? '{'
            : JSON.stringify({ version: 1, state: { recordings: [recording] } })
        )
      }
      mocks.readError = failure === 'read failure'
      const savedValues = new Map(mocks.values)

      const { useRecordingsStore, useSettingsStore } = await import('./storage')
      const { useUserStore } = await import('./userStore')
      const { useConfigStore } = await import('./configStore')
      await vi.waitFor(() => {
        for (const store of [
          useRecordingsStore,
          useSettingsStore,
          useUserStore,
          useConfigStore,
        ]) {
          expect(store.getState().hasHydrated).toBe(true)
        }
      })
      expect(useRecordingsStore.getState().recordings).toEqual([])
      expect(useSettingsStore.getState().settings).toMatchObject({
        language: 'en',
        wifiOnlyUpload: true,
      })
      expect(useUserStore.getState().user).toBeNull()
      expect(useConfigStore.getState().config).toBeNull()
      expect(mocks.values).toEqual(savedValues)
    }
  )
})
