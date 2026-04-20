import { useConfig } from '@/api/useConfig'
import { useAnalytics } from '@/features/analytics/hooks/useAnalytics'

export const AppInitialization = () => {
  const { data } = useConfig()

  useAnalytics(data?.analytics ?? {})

  return null
}
