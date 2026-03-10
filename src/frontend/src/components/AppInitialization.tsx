import { useConfig } from '@/api/useConfig'
import { useSupport } from '@/features/support/hooks/useSupport'

export const AppInitialization = () => {
  const { data } = useConfig()

  const { support = {} } = data ?? {}

  useSupport(support)

  return null
}
