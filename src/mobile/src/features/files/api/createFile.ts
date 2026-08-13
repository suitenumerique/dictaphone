import { fetchApi } from '@/api/fetchApi'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiFileItem } from '@/features/files/api/types.ts'
import { keys } from '@/api/queryKeys.ts'
import {
  createUploadId,
  type UploadProgressCallback,
  uploadFileToS3,
} from '@/utils/fileUpload'
import { type TTranscriptionLanguage } from '@/features/ai-jobs/api/types'
import { ApiError } from '@/api/ApiError'

type FileSource = {
  name: string
  type: string
  uri: string
}

export type UploadPreparedCallback = (data: {
  fileId: string
  uploadId: string
}) => void

export const finalizeFileUpload = async (
  fileId: string
): Promise<ApiFileItem> => {
  try {
    return await fetchApi<ApiFileItem>(`/files/${fileId}/upload-ended/`, {
      method: 'POST',
    })
  } catch (error) {
    // The request can time out after the backend has already finalized the
    // file. Reconcile that case instead of treating it as a failed upload.
    if (error instanceof ApiError && error.statusCode === 400) {
      const current = await fetchApi<ApiFileItem>(`/files/${fileId}/`, {
        method: 'GET',
      })
      if (
        current.upload_state === 'ready' ||
        current.upload_state === 'analyzing'
      ) {
        return current
      }
    }
    throw error
  }
}

/**
 * Upload a file while reporting native upload progress through a handler.
 *
 * @param url The URL to PUT the file to.
 * @param file The file to upload.
 */
export const uploadFile = async (
  url: string,
  file: FileSource,
  onProgress?: UploadProgressCallback,
  uploadId?: string,
  wifiOnly = false
) => {
  await uploadFileToS3(file.uri, url, file.type, onProgress, uploadId, wifiOnly)
}

/**
 * Asynchronously creates a new file and uploads it to the server.
 *
 * @param {object} params - The parameters for the file creation and upload process.
 * @param {File} params.file - The file object to be uploaded.
 * @param {function} params.onProgress - A callback function that receives the upload progress as a number (0 to 100).
 * @returns {Promise<ApiFileItem>} A promise that resolves when the file has been successfully uploaded and the server process is completed.
 */
export const createFile = async ({
  file,
  durationSeconds,
  createdAt,
  onProgress,
  onUploadPrepared,
  uploadId,
  wifiOnly = false,
  source,
  language,
}: {
  file: FileSource
  durationSeconds: number
  createdAt: string
  onProgress?: UploadProgressCallback
  onUploadPrepared?: UploadPreparedCallback
  uploadId?: string
  wifiOnly?: boolean
  source: 'mobile_recording' | 'mobile_file_upload'
  language: TTranscriptionLanguage
}): Promise<ApiFileItem> => {
  const effectiveUploadId = uploadId ?? createUploadId()
  const res = await fetchApi<ApiFileItem>(`/files/`, {
    method: 'POST',
    body: JSON.stringify({
      filename: file.name,
      type: 'audio_recording',
      duration_seconds: durationSeconds,
      created_at: createdAt,
      source,
      language,
    }),
  })
  if (res.upload_state !== 'pending') {
    throw new Error('State should be pending right after creation')
  }
  const policy = res.policy
  onUploadPrepared?.({ fileId: res.id, uploadId: effectiveUploadId })
  await uploadFile(policy, file, onProgress, effectiveUploadId, wifiOnly)
  return finalizeFileUpload(res.id)
}

export const useCreateFile = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationKey: [keys.files, 'create'],
    mutationFn: createFile,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [keys.files],
      })
    },
    onError: (error) => {
      console.error('Error creating file:', error)
    },
  })
}
