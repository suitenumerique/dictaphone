import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  addRecording: vi.fn(),
  copyExternalFile: vi.fn(),
  deleteLocalRecordingFile: vi.fn(),
  getAudioDuration: vi.fn(),
}))

vi.mock('react-native-audio-api', () => ({
  getAudioDuration: mocks.getAudioDuration,
}))

vi.mock('@react-native-documents/picker', () => ({
  errorCodes: { OPERATION_CANCELED: 'OPERATION_CANCELED' },
  isErrorWithCode: () => false,
  isKnownType: () => ({
    isKnown: true,
    mimeType: 'audio/mp4',
    UTType: 'public.mpeg-4-audio',
  }),
  pick: vi.fn(),
  types: { audio: 'audio/*' },
}))

vi.mock('@/services/configStore', () => ({
  useConfigStore: {
    getState: () => ({
      config: {
        audio_recording: {
          max_size: 10_000,
          max_duration_seconds: 100,
          allowed_extensions: ['.m4a'],
          allowed_mimetypes: ['audio/mp4'],
        },
      },
    }),
  },
}))

vi.mock('@/services/storage', () => ({
  useRecordingsStore: {
    getState: () => ({ addRecording: mocks.addRecording }),
  },
  useSettingsStore: {
    getState: () => ({
      newTranscriptionLanguage: 'fr',
      settings: { language: 'fr' },
    }),
  },
}))

vi.mock('@/utils/fileUpload', () => ({
  copyExternalFile: mocks.copyExternalFile,
}))

vi.mock('@/utils/localRecordingFile', () => ({
  deleteLocalRecordingFile: mocks.deleteLocalRecordingFile,
}))

import { queueImportedFile } from './importedFile'

describe('queueImportedFile', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.copyExternalFile.mockResolvedValue({
      path: '/documents/Imported/recording.m4a',
      name: 'recording.m4a',
      size: 2_000,
    })
    mocks.getAudioDuration.mockResolvedValue(42)
  })

  it('copies and queues a valid imported audio file with its metadata', async () => {
    await queueImportedFile({
      uri: 'content://recording',
      name: 'recording.m4a',
      type: 'audio/mp4',
      size: 2_000,
    })

    expect(mocks.copyExternalFile).toHaveBeenCalledWith(
      'content://recording',
      'recording.m4a',
      2_000
    )
    expect(mocks.addRecording).toHaveBeenCalledWith(
      expect.objectContaining({
        duration_seconds: 42,
        fileName: 'recording.m4a',
        mimeType: 'audio/mp4',
        source: 'mobile_file_upload',
        uploadingStatus: 'to_upload',
      })
    )
  })

  it('removes the copied file when duration validation fails', async () => {
    mocks.getAudioDuration.mockResolvedValue(101)

    await expect(
      queueImportedFile({
        uri: 'content://recording',
        name: 'recording.m4a',
        type: 'audio/mp4',
      })
    ).rejects.toMatchObject({ code: 'too_long' })

    expect(mocks.deleteLocalRecordingFile).toHaveBeenCalledWith(
      '/documents/Imported/recording.m4a'
    )
    expect(mocks.addRecording).not.toHaveBeenCalled()
  })

  it('maps native size-limit failures to the import size error', async () => {
    mocks.copyExternalFile.mockRejectedValue({ code: 'FILE_TOO_LARGE' })

    await expect(
      queueImportedFile({
        uri: 'content://recording',
        name: 'recording.m4a',
        type: 'audio/mp4',
        size: 2_000,
      })
    ).rejects.toMatchObject({ code: 'too_large' })

    expect(mocks.addRecording).not.toHaveBeenCalled()
  })
})
