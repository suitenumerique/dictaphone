import { useQuery } from '@tanstack/react-query'
import { useIsFocused } from '@react-navigation/native'
import { fetchApi } from '@/api/fetchApi'
import { keys } from '@/api/queryKeys'
import { useUser } from '@/features/auth/api/useUser'

export type UploadLimit = {
  count: number
  limit: number | null
}

export const uploadLimitQueryKey = [keys.files, 'upload-limit']

export function useUploadLimit() {
  const { isLoggedIn, user } = useUser()
  const isFocused = useIsFocused()
  return useQuery({
    queryKey: [...uploadLimitQueryKey, user?.id],
    queryFn: () => fetchApi<UploadLimit>('/files/upload-limit/'),
    enabled: isLoggedIn && isFocused,
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: 30_000,
  })
}
