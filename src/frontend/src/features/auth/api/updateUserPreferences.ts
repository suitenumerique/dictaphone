import { type ApiUser } from './ApiUser'
import { fetchApi } from '@/api/fetchApi'

export type ApiUserPreferences = { id: string } & Partial<
  Pick<ApiUser, 'timezone' | 'language' | 'flag_show_mobile_app_popup'>
>

export const updateUserPreferences = async ({
  user,
}: {
  user: ApiUserPreferences
}): Promise<ApiUser> => {
  const { id, ...rest } = user
  return await fetchApi(`/users/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ ...rest }),
  })
}
