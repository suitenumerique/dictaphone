import { fetchApi } from '@/api/fetchApi';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiFileItem } from '@/features/files/api/types.ts';
import { keys } from '@/api/queryKeys.ts';
import { uploadFileToS3 } from '@/utils/fileUpload';

type FileSource = {
  name: string;
  type: string;
  uri: string;
};

/**
 * Upload a file, using XHR so we can report on progress through a handler.
 *
 * @param url The URL to PUT the file to.
 * @param file The file to upload.
 */
export const uploadFile = async (
  url: string,
  file: FileSource,
) => {
  await uploadFileToS3(file.uri, url, file.type);
};

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
}: {
  file: FileSource;
  durationSeconds: number;
}): Promise<ApiFileItem> => {
  const res = await fetchApi<ApiFileItem>(`/files/`, {
    method: 'POST',
    body: JSON.stringify({
      filename: file.name,
      type: 'audio_recording',
      duration_seconds: durationSeconds,
    }),
  });
  if (res.upload_state !== 'pending') {
    throw new Error('State should be pending right after creation');
  }
  const policy = res.policy;
  await uploadFile(policy, file);
  return await fetchApi<ApiFileItem>(`/files/${res.id}/upload-ended/`, {
    method: 'POST',
  });
};

export const useCreateFile = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [keys.files, 'create'],
    mutationFn: createFile,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [keys.files],
      });
    },
    onError: error => {
      console.error('Error creating file:', error);
    },
  });
};
