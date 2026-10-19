import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/ApiError'
import {
  clearRateLimit,
  clearRateLimits,
  recordRateLimit,
} from '@/api/rateLimits'
import { markUploadEnded, transferAudioFile } from './api/createFile'
import {
  enqueueImportUploads,
  runImportUploads,
  useImportUploads,
} from './importUploads'

vi.mock('./api/createFile', () => ({
  transferAudioFile: vi.fn(),
  markUploadEnded: vi.fn(),
}))
vi.mock('@/api/queryClient', () => ({
  queryClient: { invalidateQueries: vi.fn() },
}))
vi.mock('@/features/ui/components/toaster/Toaster', () => ({
  addToast: vi.fn(),
  ToasterItem: () => null,
}))

const statuses = () =>
  Object.values(useImportUploads.getState().filesMeta).map(
    (meta) => meta.status
  )

beforeEach(() => {
  useImportUploads.setState({ step: 'none', filesMeta: {} })
  clearRateLimits()
  vi.clearAllMocks()
})

describe('import queue', () => {
  it('pauses the batch and retains finalization context until explicit resume', async () => {
    vi.mocked(transferAudioFile).mockResolvedValue('uploaded-file')
    vi.mocked(markUploadEnded)
      .mockImplementationOnce(async () => {
        recordRateLimit('upload', Date.now() + 60_000)
        throw new ApiError(429, {}, Date.now() + 60_000)
      })
      .mockResolvedValue({} as Awaited<ReturnType<typeof markUploadEnded>>)
    // Repeated names must remain distinct queue entries.
    const files = [new File(['a'], 'same.webm'), new File(['b'], 'same.webm')]
    enqueueImportUploads(
      files.map((file) => ({ file, durationSeconds: 10 })),
      'fr'
    )
    await vi.waitFor(() =>
      expect(useImportUploads.getState().step).toBe('done')
    )
    expect(statuses()).toEqual(['queued', 'queued'])
    expect(transferAudioFile).toHaveBeenCalledTimes(1)

    // An expired cooldown still waits for the user to resume uploads.
    recordRateLimit('upload', 0)
    await runImportUploads()
    expect(markUploadEnded).toHaveBeenCalledTimes(1)

    clearRateLimit('upload')
    await runImportUploads()
    expect(statuses()).toEqual(['done', 'done'])
    // The first file is only finalized again, never re-uploaded.
    expect(transferAudioFile).toHaveBeenCalledTimes(2)
    expect(vi.mocked(markUploadEnded).mock.calls).toEqual([
      ['uploaded-file'],
      ['uploaded-file'],
      ['uploaded-file'],
    ])
  })

  it('marks other failures as errors and continues with the queue', async () => {
    vi.mocked(transferAudioFile)
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue('uploaded-file')
    vi.mocked(markUploadEnded).mockResolvedValue(
      {} as Awaited<ReturnType<typeof markUploadEnded>>
    )
    enqueueImportUploads(
      [new File(['a'], 'a.webm'), new File(['b'], 'b.webm')].map((file) => ({
        file,
        durationSeconds: 10,
      })),
      'fr'
    )
    await vi.waitFor(() => expect(statuses()).toEqual(['error', 'done']))
  })
})
