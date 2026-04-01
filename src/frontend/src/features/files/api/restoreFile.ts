import { fetchApi } from '@/api/fetchApi'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys.ts'

/**
 * Restores a file specified by its unique identifier.
 *
 * @param {Object} params - The parameters required for restoring the file.
 * @param {string} params.fileId - The unique identifier of the file to be restored.
 * @returns {Promise<void>} A promise that resolves when the file is successfully restored.
 */
export const restoreFile = async ({
  fileId,
}: {
  fileId: string
}): Promise<void> => {
  await fetchApi<void>(`/files/${fileId}/restore/`, {
    method: 'POST',
  })
}

export const useRestoreFile = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: restoreFile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: [keys.files],
      })
    },
  })
}
