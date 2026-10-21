import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/ApiError'
import { UploadFinalizationNotFoundError } from '../../../api/UploadFinalizationNotFoundError'

const mocks = vi.hoisted(() => ({ fetchApi: vi.fn() }))
vi.mock('@/api/fetchApi', () => ({ fetchApi: mocks.fetchApi }))
vi.mock('@/api/ApiError', () => import('../../../api/ApiError'))
vi.mock(
  '@/api/UploadFinalizationNotFoundError',
  () => import('../../../api/UploadFinalizationNotFoundError')
)
vi.mock('@/api/queryKeys.ts', () => ({ keys: { files: 'files' } }))
vi.mock('@/utils/fileUpload', () => ({}))
vi.mock('@/api/queryClient', () => ({
  queryClient: { invalidateQueries: vi.fn() },
}))
vi.mock('./uploadLimit', () => ({
  uploadLimitQueryKey: ['files', 'upload-limit'],
}))

import { finalizeFileUpload } from './createFile'

describe('finalizeFileUpload', () => {
  beforeEach(() => vi.resetAllMocks())

  it('identifies a 404 from the finalization POST', async () => {
    mocks.fetchApi.mockRejectedValue(
      new ApiError(404, { detail: 'Not found' }, null, {
        method: 'POST',
        path: '/files/file/upload-ended/',
      })
    )
    const result = finalizeFileUpload('file')
    await expect(result).rejects.toBeInstanceOf(UploadFinalizationNotFoundError)
    await expect(result).rejects.toMatchObject({
      message: 'Api error 404 (POST /files/file/upload-ended/)',
      request: { method: 'POST', path: '/files/file/upload-ended/' },
    })
    expect(mocks.fetchApi).toHaveBeenCalledExactlyOnceWith(
      '/files/file/upload-ended/',
      {
        method: 'POST',
        rateLimitScope: 'upload',
      }
    )
  })

  it('does not treat a reconciliation GET 404 as a finalization POST 404', async () => {
    const missing = new ApiError(404, {})
    mocks.fetchApi
      .mockRejectedValueOnce(new ApiError(400, {}))
      .mockRejectedValueOnce(missing)
    await expect(finalizeFileUpload('file')).rejects.toBe(missing)
    expect(missing).not.toBeInstanceOf(UploadFinalizationNotFoundError)
    expect(mocks.fetchApi).toHaveBeenLastCalledWith('/files/file/', {
      method: 'GET',
    })
  })

  it('still reconciles a previously finalized file after a 400', async () => {
    const current = { id: 'file', upload_state: 'ready' }
    mocks.fetchApi
      .mockRejectedValueOnce(new ApiError(400, {}))
      .mockResolvedValueOnce(current)
    await expect(finalizeFileUpload('file')).resolves.toBe(current)
  })

  it.each([403, 429, 500])('preserves HTTP %s errors', async (status) => {
    const error = new ApiError(status, {})
    mocks.fetchApi.mockRejectedValue(error)
    await expect(finalizeFileUpload('file')).rejects.toBe(error)
  })
})
