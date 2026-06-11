import { z } from 'zod/v4'
import { TRANSCRIPTION_LANGUAGES } from '@/features/ai-jobs/constants'

export const transcriptionLanguageSchema = z.enum(TRANSCRIPTION_LANGUAGES)

export const uploadingStatusSchema = z.enum([
  'to_upload',
  'uploading',
  'failed',
])

export const recordingSchema = z.object({
  created_at: z.string(),
  duration_seconds: z.number().nonnegative(),
  filePath: z.string(),
  id: z.string(),
  title: z.string(),
  language: transcriptionLanguageSchema.default('fr'),
  uploadingStatus: uploadingStatusSchema,
  uploadProgress: z
    .object({
      uploadedBytes: z.number().nonnegative(),
      totalBytes: z.number().nonnegative(),
      progress: z.number().min(0).max(1),
      percentage: z.number().min(0).max(100),
    })
    .optional(),
})

export type LocalRecording = z.infer<typeof recordingSchema>
