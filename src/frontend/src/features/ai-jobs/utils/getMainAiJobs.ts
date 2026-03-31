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
