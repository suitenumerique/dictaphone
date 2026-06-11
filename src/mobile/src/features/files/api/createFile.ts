import { fetchApi } from '@/api/fetchApi'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiFileItem } from '@/features/files/api/types.ts'
import { keys } from '@/api/queryKeys.ts'
import { type UploadProgressCallback, uploadFileToS3 } from '@/utils/fileUpload'
import { type TTranscriptionLanguage } from '@/features/ai-jobs/api/types'

type FileSource = {
  name: string
  type: string
  uri: string
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
  onProgress?: UploadProgressCallback
) => {
  await uploadFileToS3(file.uri, url, file.type, onProgress)
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
  source,
  language,
}: {
  file: FileSource
  durationSeconds: number
  createdAt: string
  onProgress?: UploadProgressCallback
  source: 'mobile_recording' | 'mobile_file_upload'
  language: TTranscriptionLanguage
}): Promise<ApiFileItem> => {
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
  await uploadFile(policy, file, onProgress)
  return await fetchApi<ApiFileItem>(`/files/${res.id}/upload-ended/`, {
    method: 'POST',
  })
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
