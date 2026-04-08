import { fetchApi } from '@/api/fetchApi'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiFileItem } from '@/features/files/api/types.ts'
import { keys } from '@/api/queryKeys.ts'

/**
 * Partially update a file.
 *
 * @param {File} file - The file object to be uploaded.
 * @returns {Promise<void>} A promise that resolves when the file has been successfully uploaded and the server process is completed.
 */
export const partialUpdateFile = async (
  file: Pick<Partial<ApiFileItem>, 'title'> & Pick<ApiFileItem, 'id'>
): Promise<void> => {
  const { id, ...payload } = file
  await fetchApi<ApiFileItem>(`/files/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export const usePartialUpdateFile = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: partialUpdateFile,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [keys.files],
      })
    },
  })
}
