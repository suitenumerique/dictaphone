import { fetchApi } from './fetchApi'
import { keys } from './queryKeys'
import { useQuery } from '@tanstack/react-query'

export interface ApiConfig {
  analytics?: {
    id: string
    host: string
  }
  audio_recording: {
    upload_is_enabled: boolean
    max_size: number
    max_count_by_user: number
    allowed_extensions: string[]
    allowed_mimetypes: string[]
  }
}

const fetchConfig = (): Promise<ApiConfig> => {
  return fetchApi<ApiConfig>(`config/`)
}

export const useConfig = () => {
  return useQuery({
    queryKey: [keys.config],
    queryFn: fetchConfig,
    staleTime: Infinity,
  })
}
