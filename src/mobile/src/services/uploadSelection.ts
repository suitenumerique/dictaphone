import type { LocalRecording } from '@/types/localRecording'

export const selectRecordingToUpload = (
  recordings: LocalRecording[],
  now = Date.now()
): LocalRecording | null =>
  recordings.find(
    (recording) =>
      recording.uploadId &&
      recording.fileId &&
      (recording.uploadingStatus === 'uploading' ||
        recording.uploadingStatus === 'to_upload') &&
      (recording.uploadRetryAt === undefined || recording.uploadRetryAt <= now)
  ) ??
  recordings.find(
    (recording) =>
      recording.uploadingStatus === 'to_upload' &&
      (recording.uploadRetryAt === undefined || recording.uploadRetryAt <= now)
  ) ??
  null
