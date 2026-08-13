import type { LocalRecording } from '@/types/localRecording'

export const selectRecordingToUpload = (
  recordings: LocalRecording[]
): LocalRecording | null =>
  recordings.find(
    (recording) =>
      recording.uploadId &&
      recording.fileId &&
      recording.uploadingStatus !== 'failed'
  ) ??
  recordings.find((recording) => recording.uploadingStatus === 'to_upload') ??
  null
