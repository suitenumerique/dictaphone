import { describe, expect, it } from 'vitest'
import type { LocalRecording } from '@/types/localRecording'
import { selectRecordingToUpload } from './uploadSelection'

const createRecording = (
  id: string,
  overrides: Partial<LocalRecording> = {}
): LocalRecording => ({
  id,
  created_at: '2026-01-01T00:00:00.000Z',
  duration_seconds: 1,
  filePath: `/recordings/${id}.m4a`,
  language: 'fr',
  title: id,
  uploadingStatus: 'to_upload',
  ...overrides,
})

describe('selectRecordingToUpload', () => {
  it('skips blocked checkpoints and delayed retries while other uploads are queued', () => {
    const blocked = createRecording('blocked', {
      fileId: 'blocked-file',
      uploadId: 'blocked-upload',
      uploadingStatus: 'blocked',
    })
    const delayed = createRecording('delayed', {
      fileId: 'delayed-file',
      uploadId: 'delayed-upload',
      uploadRetryAt: 2000,
    })
    const fresh = createRecording('fresh')
    expect(selectRecordingToUpload([blocked, delayed], 1000)).toBeNull()
    expect(selectRecordingToUpload([blocked, delayed, fresh], 1000)).toBe(fresh)
    expect(selectRecordingToUpload([blocked, delayed, fresh], 2000)).toBe(
      delayed
    )
  })
  it('does not automatically resume a failed checkpoint', () => {
    const failed = createRecording('failed', {
      fileId: 'file-failed',
      uploadId: 'upload-failed',
      uploadingStatus: 'failed',
    })

    expect(selectRecordingToUpload([failed])).toBeNull()
  })

  it('prefers a resumable checkpoint over a fresh upload', () => {
    const fresh = createRecording('fresh')
    const resumable = createRecording('resumable', {
      fileId: 'file-resumable',
      uploadId: 'upload-resumable',
      uploadingStatus: 'uploading',
    })

    expect(selectRecordingToUpload([fresh, resumable])).toBe(resumable)
  })

  it('selects an explicitly retried failed recording after its status is reset', () => {
    const retried = createRecording('retried', {
      fileId: 'file-retried',
      uploadId: 'upload-retried',
      uploadingStatus: 'to_upload',
    })

    expect(selectRecordingToUpload([retried])).toBe(retried)
  })

  it('returns a fresh recording when no checkpoint exists', () => {
    const fresh = createRecording('fresh')

    expect(selectRecordingToUpload([fresh])).toBe(fresh)
  })
})
