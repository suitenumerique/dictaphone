import { z } from 'zod/v4';

export const uploadingStatusSchema = z.enum(['to_upload', 'uploading', 'failed']);

export const recordingSchema = z.object({
  createdAt: z.string(),
  durationMs: z.number(),
  filePath: z.string(),
  id: z.string(),
  name: z.string(),
  uploadingStatus: uploadingStatusSchema,
});

export type Recording = z.infer<typeof recordingSchema>;
