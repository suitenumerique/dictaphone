import { fetchApi } from '@/api/fetchApi'
import type { ListFilesResponse } from '@/features/files/api/listFiles'
import type { InfiniteData } from '@tanstack/react-query'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys.ts'

/**
 * Deletes a file specified by its unique identifier.
 *
 * @param {Object} params - The parameters required for deleting the file.
 * @param {string} params.fileId - The unique identifier of the file to be deleted.
 * @returns {Promise<void>} A promise that resolves when the file is successfully deleted.
 */
export const deleteFile = async ({
  fileId,
}: {
  fileId: string
}): Promise<void> => {
  await fetchApi<void>(`/files/${fileId}/`, {
    method: 'DELETE',
  })
}

export const useDeleteFile = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: deleteFile,
    onMutate: async ({ fileId }) => {
      await queryClient.cancelQueries({
        queryKey: [keys.files, 'infinite'],
      })

      const previousInfiniteQueries =
        queryClient.getQueriesData<InfiniteData<ListFilesResponse>>({
          queryKey: [keys.files, 'infinite'],
        })

      for (const [queryKey, currentData] of previousInfiniteQueries) {
        if (!currentData) {
          continue
        }

        let removedCount = 0
        const nextPages = currentData.pages.map((page) => {
          const nextResults = page.results.filter((file) => file.id !== fileId)
          removedCount += page.results.length - nextResults.length

          return {
            ...page,
            count: Math.max(0, page.count - (page.results.length - nextResults.length)),
            results: nextResults,
          }
        })

        if (removedCount === 0) {
          continue
        }

        queryClient.setQueryData<InfiniteData<ListFilesResponse>>(queryKey, {
          ...currentData,
          pages: nextPages,
        })
      }

      return { previousInfiniteQueries }
    },
    onError: async (_error, _variables, context) => {
      for (const [queryKey, previousData] of context?.previousInfiniteQueries ?? []) {
        queryClient.setQueryData(queryKey, previousData)
      }

      await queryClient.invalidateQueries({
        queryKey: [keys.files],
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: [keys.files],
      })
    },
  })
}
