import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import { keys } from '@/api/queryKeys'
import { useUser } from '@/features/auth/api/useUser'

export type UploadLimit = {
  count: number
  limit: number | null
}

export const uploadLimitQueryKey = [keys.files, 'upload-limit']

export function useUploadLimit() {
  const { isLoggedIn } = useUser()
  return useQuery({
    queryKey: uploadLimitQueryKey,
    queryFn: () => fetchApi<UploadLimit>('/files/upload-limit/'),
    enabled: isLoggedIn,
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: 30_000,
  })
}
