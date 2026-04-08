import { fetchApi } from '@/api/fetchApi'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys.ts'

/**
 * Hard deletes a file specified by its unique identifier.
 *
 * @param {Object} params - The parameters required for deleting the file.
 * @param {string} params.fileId - The unique identifier of the file to be hard deleted.
 * @returns {Promise<void>} A promise that resolves when the file is successfully hard deleted.
 */
export const hardDeleteFile = async ({
  fileId,
}: {
  fileId: string
}): Promise<void> => {
  await fetchApi<void>(`/files/${fileId}/hard-delete/`, {
    method: 'DELETE',
  })
}

export const useHardDeleteFile = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: hardDeleteFile,
    onSuccess: async () => {
      queryClient.invalidateQueries({
        queryKey: [keys.files],
      })
    },
  })
}
