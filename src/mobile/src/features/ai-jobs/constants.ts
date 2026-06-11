import type { TTranscriptionLanguage } from '@/features/ai-jobs/api/types'

export const TRANSCRIPTION_LANGUAGES = [
  'fr',
  'en',
  'de',
  'nl',
] as const satisfies readonly TTranscriptionLanguage[]
