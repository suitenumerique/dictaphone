import type { ApiAiJob } from '../api/types'

export function getFailureMessageKey(job: ApiAiJob | null) {
  if (job?.status !== 'failed') return null
  switch (job.failure_reason) {
    case 'AUDIO_TOO_LONG':
      return 'recordings.failures.tooLong'
    case 'RATE_LIMIT_TRANSCRIPTION_EXCEEDED':
      return 'recordings.failures.quota'
    default:
      return 'recordings.meta.processingFailed'
  }
}

export const canRetryAiJob = (job: ApiAiJob | null) =>
  !(job?.status === 'failed' && job.failure_reason === 'AUDIO_TOO_LONG')
