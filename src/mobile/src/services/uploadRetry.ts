import { ApiError } from '../api/ApiError'
import { UploadFinalizationNotFoundError } from '../api/UploadFinalizationNotFoundError'
import type { LocalRecording } from '../types/localRecording'

export const MAX_UPLOAD_ATTEMPTS = 3

export const uploadFailureUpdate = (
  recording: LocalRecording,
  error: unknown,
  now = Date.now()
): Partial<LocalRecording> => {
  if (error instanceof ApiError && error.statusCode === 429) {
    return { uploadingStatus: 'to_upload', uploadRetryAt: undefined }
  }
  const uploadAttemptCount = (recording.uploadAttemptCount ?? 0) + 1
  const retryable =
    !(error instanceof ApiError) ||
    error instanceof UploadFinalizationNotFoundError ||
    error.statusCode === 408 ||
    error.statusCode >= 500
  const uploadBlockedReason = retryable
    ? 'transient'
    : error.statusCode === 401
      ? 'authentication'
      : error.statusCode === 403
        ? 'permission'
        : 'validation'
  const blocked = !retryable || uploadAttemptCount >= MAX_UPLOAD_ATTEMPTS
  return {
    uploadAttemptCount,
    uploadingStatus: blocked ? 'blocked' : 'to_upload',
    uploadBlockedReason: blocked ? uploadBlockedReason : undefined,
    uploadRetryAt: blocked
      ? undefined
      : now + 1000 * 2 ** (uploadAttemptCount - 1),
  }
}

export const resetUploadRetry = (): Partial<LocalRecording> => ({
  uploadingStatus: 'to_upload',
  uploadAttemptCount: 0,
  uploadBlockedReason: undefined,
  uploadRetryAt: undefined,
  uploadProgress: undefined,
})

export const restoreUploadAfterRestart = (
  recording: LocalRecording
): LocalRecording => {
  if (
    recording.uploadingStatus === 'blocked' &&
    recording.uploadBlockedReason !== 'transient'
  ) {
    return { ...recording, uploadProgress: undefined }
  }
  return {
    ...recording,
    ...resetUploadRetry(),
    uploadingStatus:
      recording.uploadId && recording.fileId ? 'uploading' : 'to_upload',
  }
}
