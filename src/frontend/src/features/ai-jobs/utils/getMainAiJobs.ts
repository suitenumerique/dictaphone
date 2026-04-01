import { ApiAiJob } from '@/features/ai-jobs/api/types.ts'

/**
 * Get the main ai jobs (transcript and summary)
 * @param aiJobs
 */
export function getMainAiJobs(aiJobs: ApiAiJob[] | undefined) {
  if (!aiJobs)
    return {
      lastAiJobTranscript: null,
      lastAiJobSummary: null,
    }
  return {
    lastAiJobTranscript: aiJobs.find((el) => el.type === 'transcript') ?? null,
    lastAiJobSummary: aiJobs.find((el) => el.type === 'summary') ?? null,
  }
}

/**
 * Main jobs are considered unresolved when one is still pending or missing.
 */
export function shouldRefetchMainAiJobs(aiJobs: ApiAiJob[] | undefined) {
  const { lastAiJobTranscript, lastAiJobSummary } = getMainAiJobs(aiJobs)
  if (!lastAiJobTranscript) return true
  if (lastAiJobTranscript.status === 'pending') return true
  if (lastAiJobTranscript.status === 'failed') return false
  if (!lastAiJobSummary) return true
  if (lastAiJobSummary.status === 'pending') return true
  if (lastAiJobSummary.status === 'failed') return false
  return true
}
