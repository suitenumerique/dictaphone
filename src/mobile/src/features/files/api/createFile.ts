import { fetchApi } from '@/api/fetchApi';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiFileItem } from '@/features/files/api/types.ts';
import { keys } from '@/api/queryKeys.ts';
import {
  uploadFiles,
  stat,
} from '@dr.pogodin/react-native-fs';

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
 * @param progressHandler A handler that receives progress updates as a single integer `0 <= x <= 100`.
 */
export const uploadFile = async (
  url: string,
  file: FileSource,
  progressHandler: (progress: number) => void,
) => {
  console.log({url, file})
  const fileStat = await stat(file.uri)

  return await uploadFiles({
    toUrl: url,
    files: [
      {
        name: file.name,
        filepath: fileStat.originalFilepath,
        filetype: file.type,
        filename: file.name,
      },
    ],
    method: 'PUT',
    headers: {
      'X-amz-acl': 'private',
      'Content-Type': file.type,
    },
    progress: el =>
      progressHandler((100 * el.totalBytesSent) / el.totalBytesExpectedToSend),
  }).promise;
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
  onProgress,
}: {
  file: FileSource;
  durationSeconds: number;
  onProgress: (progress: number) => void;
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
  await uploadFile(policy, file, onProgress);
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
