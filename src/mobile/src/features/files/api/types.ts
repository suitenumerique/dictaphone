import { ApiAiJob } from '@/features/ai-jobs/api/types.ts'

export type ApiFileCreator = {
  id: string // UUID
  full_name: string | null
  short_name: string | null
}

export type ApiFileType = 'audio_recording'
export type ApiFileUploadState = 'pending' | 'ready'

export type ApiFileItem = {
  id: string // UUID
  created_at: string // ISO datetime string
  updated_at: string // ISO datetime string
  title: string
  type: ApiFileType
  creator: ApiFileCreator
  deleted_at: string | null
  hard_deleted_at: string | null
  filename: string
  upload_state: ApiFileUploadState
  mimetype: string // e.g. "image/png"
  size: number // file size in bytes
  description: string | null
  duration_seconds: number
  ai_jobs: ApiAiJob[]
  abilities: {
    destroy: boolean
    partial_update: boolean
    restore: boolean
    hard_delete: boolean
    // ...
  }
} & (
  | {
      upload_state: 'ready'
      url: string
    }
  | {
      upload_state: 'pending'
      policy: string
      url: null
    }
)
