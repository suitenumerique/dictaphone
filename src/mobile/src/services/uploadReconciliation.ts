import type { NativeUploadStatus } from '../utils/fileUpload'
import type { LocalRecording } from '../types/localRecording'
import { ApiError } from '../api/ApiError'

/**
 * A native upload can finish while the API finalization request is still pending.
 * That is a recoverable state, not an upload failure.
 */
export const hasFinishedNativeUpload = (
  nativeStatus: Pick<NativeUploadStatus, 'status'> | undefined,
  waitForUploadCompleted = false
): boolean =>
  waitForUploadCompleted || nativeStatus?.status === 'uploadedAwaitingFinalize'

export const isRetryableUploadError = (error: unknown): boolean =>
  !(error instanceof ApiError) ||
  error.statusCode === 408 ||
  error.statusCode === 429 ||
  error.statusCode >= 500

export const statusAfterUploadError = (
  nativeStatus: Pick<NativeUploadStatus, 'status'> | undefined,
  waitForUploadCompleted = false,
  error?: unknown
): LocalRecording['uploadingStatus'] =>
  hasFinishedNativeUpload(nativeStatus, waitForUploadCompleted) &&
  (error === undefined || isRetryableUploadError(error))
    ? 'uploading'
    : 'failed'
