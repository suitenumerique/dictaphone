import { useMutation, useQuery } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys'
import { fetchUser } from './fetchUser'
import { type ApiUser } from './ApiUser'
import { useCallback, useEffect, useMemo } from 'react'
import { logoutUrl } from '../utils/logoutUrl'
import { useConfig } from '@/api/useConfig'
import { updateUserPreferences } from '@/features/auth/api/updateUserPreferences'
import { queryClient } from '@/api/queryClient'
import {
  startAnalyticsSession,
  terminateAnalyticsSession,
} from '@/features/analytics/hooks/useAnalytics'

type TUserInfo = {
  refetch: () => void
  isLoading: boolean
  logout: () => void
} & (
  | {
      isLoggedIn: false
      user: undefined
      updateUser: undefined
    }
  | {
      isLoggedIn: true
      user: ApiUser
      updateUser: (
        userInfo: Partial<
          Pick<ApiUser, 'language' | 'flag_show_mobile_app_popup'>
        >
      ) => void
    }
)

/**
 * returns info about currently logged-in user
 *
 * `isLoggedIn` is undefined while query is loading and true/false when it's done
 */
export const useUser = (
  opts: {
    fetchUserOptions?: Parameters<typeof fetchUser>[0]
  } = {}
) => {
  const { isLoading: isConfigLoading } = useConfig()

  const options = useMemo(() => {
    if (isConfigLoading) return
    return opts.fetchUserOptions
  }, [opts, isConfigLoading])

  const query = useQuery({
    // eslint-disable-next-line @tanstack/query/exhaustive-deps
    queryKey: [keys.user],
    queryFn: () => fetchUser(options),
    staleTime: Infinity,
    enabled: !isConfigLoading,
  })

  const updateUserQuery = useMutation({
    mutationFn: updateUserPreferences,
    onSuccess: (data) => {
      queryClient.setQueryData([keys.user], data)
    },
  })

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const updateUser = (
    newData: Partial<Pick<ApiUser, 'language' | 'flag_show_mobile_app_popup'>>
  ) => {
    if (!query.data) return

    const currentUser = query.data as ApiUser
    updateUserQuery.mutate({
      user: {
        id: currentUser.id,
        timezone: currentUser.timezone,
        ...newData,
      },
    })
  }

  useEffect(() => {
    if (query?.data) {
      startAnalyticsSession(query.data)
      // initializeSupportSession(query.data)
    }
  }, [query.data])

  const logout = useCallback(() => {
    // terminateSupportSession()
    terminateAnalyticsSession()
    window.location.href = logoutUrl()
  }, [])

  const isLoggedIn = query.status === 'success' && query.data !== false

  return useMemo<TUserInfo>(
    () =>
      ({
        refetch: query.refetch,
        ...(isLoggedIn
          ? {
              isLoggedIn: true,
              user: query.data as ApiUser,
              updateUser,
            }
          : { isLoggedIn: false, updateUser: undefined, user: undefined }),
        isLoading: query.isLoading,
        logout,
      }) as TUserInfo,
    [query.refetch, query.data, query.isLoading, isLoggedIn, logout, updateUser]
  )
}
