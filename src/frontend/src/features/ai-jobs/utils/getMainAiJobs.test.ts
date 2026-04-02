import { describe, expect, it } from 'vitest'
import { getMainAiJobs, shouldRefetchMainAiJobs } from './getMainAiJobs.ts'
import type { ApiAiJob } from '@/features/ai-jobs/api/types.ts'

function createJob(
  type: ApiAiJob['type'],
  status: ApiAiJob['status']
): ApiAiJob {
  return {
    id: `${type}-${status}`,
    type,
    status,
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
  }
}

describe('getMainAiJobs', () => {
  it('returns null jobs when aiJobs is undefined', () => {
    expect(getMainAiJobs(undefined)).toEqual({
      lastAiJobTranscript: null,
      lastAiJobSummary: null,
    })
  })

  it('returns transcript and summary jobs when present', () => {
    const aiJobs = [
      createJob('summary', 'success'),
      createJob('transcript', 'success'),
    ]
    expect(getMainAiJobs(aiJobs)).toEqual({
      lastAiJobTranscript: aiJobs[1],
      lastAiJobSummary: aiJobs[0],
    })
  })
})

describe('shouldRefetchMainAiJobs', () => {
  it('returns true when a main job is missing', () => {
    expect(shouldRefetchMainAiJobs([createJob('summary', 'success')])).toBe(
      true
    )
  })

  it('returns true when a main job is pending', () => {
    expect(
      shouldRefetchMainAiJobs([
        createJob('summary', 'success'),
        createJob('transcript', 'pending'),
      ])
    ).toBe(true)
  })

  it('returns false when both main jobs are finished', () => {
    expect(
      shouldRefetchMainAiJobs([
        createJob('summary', 'success'),
        createJob('transcript', 'failed'),
      ])
    ).toBe(false)
  })

  it('Bug real case', () => {
    expect(
      shouldRefetchMainAiJobs([
        createJob('summary', 'success'),
        createJob('transcript', 'success'),
      ])
    ).toBe(false)
  })
})
