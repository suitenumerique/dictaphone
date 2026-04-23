import { useConfig } from '@/api/useConfig'
import { useAnalytics } from '@/features/analytics/hooks/useAnalytics'

export const AppInitialization = ({
  children,
}: {
  children: React.ReactNode
}) => {
  const { data } = useConfig()

  useAnalytics(data?.analytics ?? {})

  return children
}
