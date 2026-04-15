import { z } from 'zod/v4';

export const uploadingStatusSchema = z.enum(['to_upload', 'uploading', 'failed']);

export const recordingSchema = z.object({
  created_at: z.string(),
  duration_seconds: z.number().nonnegative(),
  filePath: z.string(),
  id: z.string(),
  title: z.string(),
  uploadingStatus: uploadingStatusSchema,
});

export type LocalRecording = z.infer<typeof recordingSchema>;
