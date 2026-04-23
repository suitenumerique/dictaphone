import { useEffect } from 'react'
import { ApiUser } from '@/features/auth/api/ApiUser'
import { PostHog } from 'posthog-react-native'

let posthog: PostHog | null = null

export const startAnalyticsSession = (data: ApiUser) => {
  if (posthog === null) return
  // @ts-expect-error copied from meet code
  if (posthog._isIdentified()) return
  const { id, email } = data
  posthog.identify(id, { email })
}

export const terminateAnalyticsSession = () => {
  if (posthog === null) return
  // @ts-expect-error copied from meet code
  if (!posthog._isIdentified()) return
  posthog.reset()
}

export type useAnalyticsProps = {
  id?: string
  host?: string
  isDisabled?: boolean
}

export const useAnalytics = ({ id, host, isDisabled }: useAnalyticsProps) => {
  useEffect(() => {
    if (!id || !host || isDisabled) return
    if (posthog !== null) return
    posthog = new PostHog(id, {
      host: host,
      personProfiles: 'always',
    })
  }, [id, host, isDisabled])
  return null
}

export function logPosthogScreenChange(screen: string) {
  if (posthog === null) return
  posthog.screen(screen)
}
