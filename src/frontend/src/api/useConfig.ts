import { fetchApi } from './fetchApi'
import { keys } from './queryKeys'
import { useQuery } from '@tanstack/react-query'

export interface ApiConfig {
  LANGUAGE_CODE: string
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
    max_duration_seconds: number
  }
  mobile_app: {
    ios_download_link: string
    android_download_link: string
  }
  data_policy: {
    file_auto_hard_delete_after_days: number
    original_file_data_delete_after_days: number
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
