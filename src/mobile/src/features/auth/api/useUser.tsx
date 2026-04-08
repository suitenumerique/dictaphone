import { useMutation, useQuery } from '@tanstack/react-query';
import { keys } from '@/api/queryKeys';
import { fetchUser } from './fetchUser';
import { type ApiUser } from './ApiUser';
import { useMemo } from 'react';
import { useConfig } from '@/api/useConfig';
import { updateUserPreferences } from '@/features/auth/api/updateUserPreferences';
import { queryClient } from '@/api/queryClient';

type TUserInfo = {
  refetch: () => void;
  isLoading: boolean;
  // logout: () => void;
} & (
  | {
      isLoggedIn: false;
      user: undefined;
      updateUser: undefined;
    }
  | {
      isLoggedIn: true;
      user: ApiUser;
      updateUser: (userInfo: Pick<ApiUser, 'language'>) => void;
    }
);

/**
 * returns info about currently logged-in user
 *
 * `isLoggedIn` is undefined while query is loading and true/false when it's done
 */
export const useUser = () => {
  const { isLoading: isConfigLoading } = useConfig();

  const query = useQuery({
    queryKey: [keys.user],
    queryFn: () => fetchUser(),
    staleTime: Infinity,
    enabled: !isConfigLoading,
  });

  const updateUserQuery = useMutation({
    mutationFn: updateUserPreferences,
    onSuccess: data => {
      queryClient.setQueryData([keys.user], data);
    },
  });

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const updateUser = (newData: Pick<ApiUser, 'language'>) => {
    if (!query.data) return;

    const currentUser = query.data as ApiUser;
    updateUserQuery.mutate({
      user: {
        id: currentUser.id,
        timezone: currentUser.timezone,
        ...newData,
      },
    });
  };

  const isLoggedIn = query.status === 'success' && query.data !== false;

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
        // logout,
      } as TUserInfo),
    [query.refetch, query.data, query.isLoading, isLoggedIn, updateUser],
  );
};
