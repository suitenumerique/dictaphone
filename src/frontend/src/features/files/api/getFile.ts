import { fetchApi } from '@/api/fetchApi'
import { useQuery } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys'
import { ApiFileItem } from '@/features/files/api/types.ts'
import { ApiError } from '@/api/ApiError.ts'
import { shouldRefetchMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs.ts'

const REFRESH_AI_JOBS_INTERVAL_MS = 10_000

export const getFile = async (fileId: string): Promise<ApiFileItem | null> => {
  try {
    return await fetchApi<ApiFileItem>(`/files/${fileId}/`, {
      method: 'GET',
    })
  } catch (e) {
    if (e instanceof ApiError && e.statusCode === 404) {
      return null
    }
    throw new Error(
      `Failed to fetch file with id ${fileId}: ${e instanceof Error ? e.message : 'Unknown error'}`
    )
  }
}

export const useGetFile = (params: Parameters<typeof getFile>[0]) => {
  return useQuery({
    queryKey: [keys.files, params],
    queryFn: () => getFile(params),
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: (query) => {
      const file = query.state.data
      if (!file) {
        return false
      }
      return shouldRefetchMainAiJobs(file.ai_jobs)
        ? REFRESH_AI_JOBS_INTERVAL_MS
        : false
    },
  })
}
