import { create } from 'zustand'
import i18n from 'i18next'
import { markUploadEnded, transferAudioFile } from './api/createFile'
import type { TranscriptionLanguage } from '@/features/settings/settingsStore'
import { areUploadsPaused, isRateLimitError } from '@/api/rateLimits'
import { queryClient } from '@/api/queryClient'
import { keys } from '@/api/queryKeys'
import { addToast, ToasterItem } from '@/features/ui/components/toaster/Toaster'

export type FileUploadMeta = {
  file: File
  durationSeconds: number
  language: TranscriptionLanguage
  createdAt: string
  progress: number
  // Queued files wait while uploads are paused by a rate limit.
  status: 'queued' | 'uploading' | 'done' | 'error'
  // Set once the audio is stored, so a throttled finalization never re-uploads it.
  finalizationFileId?: string
}
export type UploadingState = {
  step: 'none' | 'preparing' | 'upload_files' | 'done'
  filesMeta: Record<string, FileUploadMeta>
}

// Lives outside React so imports continue across navigation.
export const useImportUploads = create<UploadingState>(() => ({
  step: 'none',
  filesMeta: {},
}))

function updateFile(id: string, patch: Partial<FileUploadMeta>) {
  useImportUploads.setState((state) =>
    state.filesMeta[id]
      ? {
          filesMeta: {
            ...state.filesMeta,
            [id]: { ...state.filesMeta[id], ...patch },
          },
        }
      : state
  )
}

let running = false
/** Uploads queued files sequentially: the backend does not support concurrent uploads. */
export async function runImportUploads() {
  if (running) return
  running = true
  try {
    while (!areUploadsPaused()) {
      const next = Object.entries(useImportUploads.getState().filesMeta).find(
        ([, meta]) => meta.status === 'queued'
      )
      if (!next) break
      const [id, meta] = next
      updateFile(id, { status: 'uploading' })
      try {
        let fileId = meta.finalizationFileId
        if (!fileId) {
          fileId = await transferAudioFile({
            ...meta,
            source: 'web_file_upload',
            onProgress: (progress) => updateFile(id, { progress }),
          })
          updateFile(id, { finalizationFileId: fileId })
        }
        await markUploadEnded(fileId)
        updateFile(id, { status: 'done', progress: 100 })
        void queryClient.invalidateQueries({ queryKey: [keys.files] })
      } catch (error) {
        if (isRateLimitError(error)) {
          // Uploads are now paused: keep the file queued until the user resumes.
          updateFile(id, { status: 'queued' })
        } else {
          updateFile(id, { status: 'error' })
          addToast(
            <ToasterItem type="error">
              {i18n.t('upload:errors.uploadFailed')}
            </ToasterItem>
          )
        }
      }
    }
  } finally {
    running = false
    useImportUploads.setState({ step: 'done' })
  }
}

export function enqueueImportUploads(
  files: { file: File; durationSeconds: number }[],
  language: TranscriptionLanguage
) {
  const entries = files.map(({ file, durationSeconds }) => [
    // Files with the same name must remain distinct entries.
    crypto.randomUUID(),
    {
      file,
      durationSeconds,
      language,
      createdAt: new Date().toISOString(),
      progress: 0,
      status: 'queued',
    } satisfies FileUploadMeta,
  ])
  useImportUploads.setState((state) => ({
    step: 'upload_files',
    filesMeta: {
      ...Object.fromEntries(
        Object.entries(state.filesMeta).filter(
          ([, meta]) => meta.status === 'queued' || meta.status === 'uploading'
        )
      ),
      ...Object.fromEntries(entries),
    },
  }))
  void runImportUploads()
}
