import { fetchApi } from './fetchApi'
import { keys } from './queryKeys'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import {
  ConfigStore,
  DEFAULT_DATA_POLICY,
  DEFAULT_MAX_RECORDING_DURATION_SECONDS,
  useConfigStore,
} from '@/services/configStore'
import { useUser } from '@/features/auth/api/useUser'

export interface ApiConfig {
  analytics?: {
    id: string
    host: string
  }
  audio_recording: {
    upload_is_enabled: boolean
    max_size: number
    // might not exist yet in prod
    max_duration_seconds?: number
    max_count_by_user: number
    allowed_extensions: string[]
    allowed_mimetypes: string[]
  }
  mobile_app: {
    ios_download_link: string
    android_download_link: string
    ios_version: string
    ios_min_version: string
    android_version: string
    android_min_version: string
  }
  docs_integration_enabled: boolean
  docs_integration_supports_synchroneous_calls?: boolean
  data_policy: {
    original_file_data_delete_after_days: number
    file_auto_hard_delete_after_days: number
    is_relative_to_user?: boolean
  }
}

const fetchConfig = async (): Promise<ConfigStore['config']> => {
  try {
    const config = await fetchApi<ApiConfig>(`config/`)
    const cleanedConfig: ConfigStore['config'] = {
      ...config,
      audio_recording: {
        ...config.audio_recording,
        max_duration_seconds:
          config.audio_recording.max_duration_seconds ??
          DEFAULT_MAX_RECORDING_DURATION_SECONDS,
      },
      docs_integration_enabled: config.docs_integration_enabled ?? false,
      docs_integration_supports_synchroneous_calls:
        config.docs_integration_supports_synchroneous_calls ?? false,
      data_policy: {
        original_file_data_delete_after_days:
          config.data_policy.original_file_data_delete_after_days ??
          DEFAULT_DATA_POLICY.original_file_data_delete_after_days,
        file_auto_hard_delete_after_days:
          config.data_policy.file_auto_hard_delete_after_days ??
          DEFAULT_DATA_POLICY.file_auto_hard_delete_after_days,
        is_relative_to_user: config.data_policy.is_relative_to_user,
      },
    }
    useConfigStore.getState().setCachedConfig(cleanedConfig)
    return cleanedConfig
  } catch (error) {
    const cachedConfig = useConfigStore.getState().config
    if (cachedConfig) {
      console.warn('Using cached config after config fetch failure:', error)
      return cachedConfig
    }
    throw error
  }
}

export const useConfig = () => {
  const hasHydrated = useConfigStore((state) => state.hasHydrated)
  const { isLoggedIn, user } = useUser()
  const previousUserId = useRef<string | undefined>(undefined)
  const hasRefetchedAfterLogin = useRef(false)

  const configQuery = useQuery({
    queryKey: [keys.config],
    queryFn: fetchConfig,
    placeholderData: () => useConfigStore.getState().config ?? undefined,
    staleTime: 10 * 60 * 1000,
    enabled: hasHydrated,
  })
  const { refetch: refetchConfig } = configQuery

  const isRelativeToUser = configQuery.data?.data_policy?.is_relative_to_user
  const userId = user?.id

  useEffect(() => {
    if (!hasHydrated) {
      return
    }

    const userChanged = previousUserId.current !== userId
    previousUserId.current = userId

    if (userChanged) {
      hasRefetchedAfterLogin.current = isLoggedIn
      void refetchConfig()
      return
    }

    if (!isLoggedIn) {
      hasRefetchedAfterLogin.current = false
      return
    }

    if (
      hasRefetchedAfterLogin.current ||
      isRelativeToUser === undefined ||
      isRelativeToUser === true
    ) {
      return
    }

    hasRefetchedAfterLogin.current = true
    void refetchConfig()
  }, [hasHydrated, isLoggedIn, isRelativeToUser, refetchConfig, userId])

  return configQuery
}
