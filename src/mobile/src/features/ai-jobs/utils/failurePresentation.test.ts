import { describe, expect, it } from 'vitest'
import type { ApiAiJob } from '../api/types'
import { canRetryAiJob, getFailureMessageKey } from './failurePresentation'

const job = (
  failure_reason?: ApiAiJob['failure_reason'],
  status: ApiAiJob['status'] = 'failed'
) => ({ status, failure_reason }) as ApiAiJob

describe('AI job failures', () => {
  it('explains excessive duration and prevents retries', () => {
    expect(getFailureMessageKey(job('AUDIO_TOO_LONG'))).toBe(
      'recordings.failures.tooLong'
    )
    expect(canRetryAiJob(job('AUDIO_TOO_LONG'))).toBe(false)
  })
  it('explains audio quota failures and allows a later retry', () => {
    expect(getFailureMessageKey(job('RATE_LIMIT_TRANSCRIPTION_EXCEEDED'))).toBe(
      'recordings.failures.quota'
    )
    expect(canRetryAiJob(job('RATE_LIMIT_TRANSCRIPTION_EXCEEDED'))).toBe(true)
  })
  it('handles old and unknown failure reasons', () => {
    expect(getFailureMessageKey(job())).toBe('recordings.meta.processingFailed')
    expect(getFailureMessageKey(job('FUTURE_REASON'))).toBe(
      'recordings.meta.processingFailed'
    )
    expect(getFailureMessageKey(job(undefined, 'success'))).toBeNull()
    expect(getFailureMessageKey(null)).toBeNull()
  })
})
