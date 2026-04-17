import { useMutation, useQuery } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys'
import { fetchUser } from './fetchUser'
import { type ApiUser } from './ApiUser'
import { useCallback, useMemo } from 'react'
import { updateUserPreferences } from '@/features/auth/api/updateUserPreferences'
import { queryClient } from '@/api/queryClient'
import { fetchApi } from '@/api/fetchApi'
import { clearAuthCookies } from '@/services/authService'
import { useUserStore } from '@/services/storage'

type TUserInfo = {
  refetch: () => void
  isLoading: boolean
  logout: () => Promise<void>
} & (
  | {
      isLoggedIn: false
      user: undefined
      updateUser: undefined
    }
  | {
      isLoggedIn: true
      user: ApiUser
      updateUser: (userInfo: Pick<ApiUser, 'language'>) => void
    }
)

/**
 * returns info about currently logged-in user
 *
 * `isLoggedIn` is undefined while query is loading and true/false when it's done
 */
export const useUser = () => {
  const { setCachedUser, clearCachedUser } = useUserStore()

  const query = useQuery({
    queryKey: [keys.user],
    queryFn: () => fetchUser(),
    staleTime: Infinity,
  })

  const updateUserQuery = useMutation({
    mutationFn: updateUserPreferences,
    onSuccess: (data) => {
      setCachedUser(data)
      queryClient.setQueryData([keys.user], data)
    },
  })

  const logoutQuery = useMutation({
    mutationFn: async () => {
      try {
        const response = await fetchApi<string>('/logout/')

        const html = String(response ?? '')

        const actionMatch = html.match(/<form[^>]*action="([^"]+)"/i)
        const xsrfMatch = html.match(/name="xsrf"\s+value="([^"]+)"/i)
        const logoutMatch = html.match(/name="logout"\s+value="([^"]+)"/i)

        const action = actionMatch?.[1]
        const xsrf = xsrfMatch?.[1]
        const logout = logoutMatch?.[1]

        if (action && xsrf && logout) {
          const body = new URLSearchParams({
            xsrf,
            logout,
          })

          await fetch(action, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: body.toString(),
          })
        }
      } catch (error) {
        console.warn(
          'Logout endpoint failed, clearing local auth state.',
          error
        )
      } finally {
        await clearAuthCookies()
        clearCachedUser()
        queryClient.resetQueries()
      }
    },
  })

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const updateUser = (newData: Pick<ApiUser, 'language'>) => {
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

  const logout = useCallback(async () => {
    await logoutQuery.mutateAsync()
    // eslint-disable-next-line @tanstack/query/no-unstable-deps
  }, [logoutQuery])

  const isLoggedIn = query.status === 'success' && query.data !== false

  return useMemo<TUserInfo>(
    () =>
      ({
        refetch: query.refetch,
        logout,
        ...(isLoggedIn
          ? {
              isLoggedIn: true,
              user: query.data as ApiUser,
              updateUser,
            }
          : { isLoggedIn: false, updateUser: undefined, user: undefined }),
        isLoading: query.isLoading,
      }) as TUserInfo,
    [query.refetch, query.data, query.isLoading, isLoggedIn, logout, updateUser]
  )
}
