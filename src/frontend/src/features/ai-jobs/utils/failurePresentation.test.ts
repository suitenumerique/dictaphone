import { describe, expect, it } from 'vitest'
import type { ApiAiJob } from '../api/types'
import { canRetryAiJob, getFailureMessageKey } from './failurePresentation'

const job = (
  failure_reason?: string,
  status: ApiAiJob['status'] = 'failed'
): ApiAiJob => ({
  id: 'job',
  type: 'transcript',
  status,
  failure_reason,
  created_at: '',
  updated_at: '',
  language: 'fr',
  docs_app_id: null,
  processing_expected_end_at: null,
})

describe('failure presentation', () => {
  it('explains long audio and removes retry', () => {
    expect(getFailureMessageKey(job('AUDIO_TOO_LONG'))).toBe('failures.tooLong')
    expect(canRetryAiJob(job('AUDIO_TOO_LONG'))).toBe(false)
  })
  it('explains quota failures and allows manual retry', () => {
    expect(getFailureMessageKey(job('RATE_LIMIT_TRANSCRIPTION_EXCEEDED'))).toBe(
      'failures.quota'
    )
    expect(canRetryAiJob(job('RATE_LIMIT_TRANSCRIPTION_EXCEEDED'))).toBe(true)
  })
  it.each([undefined, '', 'UNKNOWN_FAILURE', 'FUTURE_REASON'])(
    'falls back safely for %s',
    (reason) => {
      expect(getFailureMessageKey(job(reason))).toBe('transcript.status.failed')
      expect(canRetryAiJob(job(reason))).toBe(true)
    }
  )
  it('does not show failure messages for non-failed jobs', () => {
    expect(getFailureMessageKey(job('AUDIO_TOO_LONG', 'success'))).toBeNull()
    expect(getFailureMessageKey(null)).toBeNull()
  })
})
