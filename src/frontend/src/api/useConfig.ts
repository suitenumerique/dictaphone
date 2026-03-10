import { fetchApi } from './fetchApi'
import { keys } from './queryKeys'
import { useQuery } from '@tanstack/react-query'

export interface ApiConfig {
  support?: {
    id: string
    help_article_transcript: string
    help_article_recording: string
    help_article_more_tools: string
  }
  feedback: {
    url: string
  }
  use_proconnect_button?: boolean
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
