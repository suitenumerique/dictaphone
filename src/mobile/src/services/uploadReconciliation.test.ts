import { describe, expect, it } from 'vitest'
import {
  hasFinishedNativeUpload,
  isRetryableUploadError,
  statusAfterUploadError,
} from './uploadReconciliation'
import { ApiError } from '../api/ApiError'

describe('upload reconciliation', () => {
  it('considers a native completed upload recoverable while finalization is pending', () => {
    const status = { status: 'uploadedAwaitingFinalize' as const }

    expect(hasFinishedNativeUpload(status)).toBe(true)
    expect(statusAfterUploadError(status)).toBe('uploading')
  })

  it('considers a wait that resolved successfully recoverable', () => {
    expect(hasFinishedNativeUpload({ status: 'uploading' }, true)).toBe(true)
    expect(statusAfterUploadError({ status: 'uploading' }, true)).toBe(
      'uploading'
    )
  })

  it('keeps genuine native failures failed', () => {
    expect(statusAfterUploadError({ status: 'failed' })).toBe('failed')
    expect(statusAfterUploadError(undefined)).toBe('failed')
  })

  it('only keeps finalization errors pending when they are retryable', () => {
    const status = { status: 'uploadedAwaitingFinalize' as const }

    expect(
      isRetryableUploadError(new TypeError('Network request failed'))
    ).toBe(true)
    expect(statusAfterUploadError(status, false, new TypeError())).toBe(
      'uploading'
    )
    expect(statusAfterUploadError(status, false, new ApiError(400, {}))).toBe(
      'failed'
    )
  })
})
