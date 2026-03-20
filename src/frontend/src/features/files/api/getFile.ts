import { fetchApi } from '@/api/fetchApi'
import { useQuery } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys'
import { ApiFileItem } from '@/features/files/api/types.ts'

export const getFile = async (fileId: string): Promise<ApiFileItem> => {
  return fetchApi<ApiFileItem>(`/files/${fileId}/`, {
    method: 'GET',
  })
}

export const useGetFile = (params: Parameters<typeof getFile>[0]) => {
  return useQuery({
    queryKey: [keys.files, params],
    queryFn: () => getFile(params),
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
  })
}
