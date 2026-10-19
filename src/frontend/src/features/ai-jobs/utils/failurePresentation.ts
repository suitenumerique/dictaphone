import type { ApiAiJob } from '../api/types'

export function getFailureMessageKey(job: ApiAiJob | null) {
  if (job?.status !== 'failed') return null
  switch (job.failure_reason) {
    case 'AUDIO_TOO_LONG':
      return 'failures.tooLong'
    case 'RATE_LIMIT_TRANSCRIPTION_EXCEEDED':
      return 'failures.quota'
    default:
      return 'transcript.status.failed'
  }
}

export const canRetryAiJob = (job: ApiAiJob | null) =>
  !(job?.status === 'failed' && job.failure_reason === 'AUDIO_TOO_LONG')
