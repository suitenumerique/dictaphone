export type RecorderLifecycleState =
  | 'idle'
  | 'starting'
  | 'recording'
  | 'paused'
  | 'stopping'
  | 'stopped'
  | 'error'

export type RecorderChunk = {
  sequenceNumber: number
  timestamp: number
  blob: Blob
}

export type StoredRecordingStatus =
  | 'recording'
  | 'paused'
  | 'stopped'
  | 'uploading'
  | 'exited'
  | 'upload_failed'

export type StoredRecording = {
  id: string
  createdAt: number
  updatedAt: number
  filename: string
  mimeType: string
  status: StoredRecordingStatus
  chunkCount: number
  totalBytes: number
  durationMs: number
  uploadProgress: number
  uploadError: string | null
}

export type StoredChunk = {
  id?: number
  recordingId: string
  sequenceNumber: number
  timestamp: number
  blob: Blob
}

export type UploadProgress = {
  uploadedBytes: number
  totalBytes: number
  percent: number
}

export type UploadResult = {
  ok: boolean
  status: number
  responseText?: string
}

export type UploadOptions = {
  recordingId: string
  url: string
  method?: 'POST' | 'PUT'
  totalBytes: number
  contentType?: string
  headers?: Record<string, string>
  signal?: AbortSignal
  onProgress?: (progress: UploadProgress) => void
}
