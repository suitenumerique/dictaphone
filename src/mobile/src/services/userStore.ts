import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { z } from 'zod/v4'
import { mmkvStorage } from '@/services/index'
import i18n from '@/i18n'
import { type ApiUser } from '@/features/auth/api/ApiUser'
import omit from '@/utils/omit'

const apiUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  language: z.enum(['fr-fr', 'en-us']),
  timezone: z.string(),
})

export interface UserStore {
  hasHydrated: boolean
  user: ApiUser | null
  authExpired: boolean
  setAuthExpired: (expired: boolean) => void
  setCachedUser: (user: ApiUser) => void
  clearCachedUser: () => void
}
export const useUserStore = create<UserStore>()(
  persist(
    (set) => ({
      hasHydrated: false,
      user: null,
      authExpired: false,
      setAuthExpired: (expired) => set({ authExpired: expired }),
      setCachedUser: (user) => set({ user, authExpired: false }),
      clearCachedUser: () => set({ user: null }),
    }),
    {
      name: 'user-info',
      storage: createJSONStorage(() => mmkvStorage),
      version: 1,
      partialize: (state) => omit(state, ['hasHydrated', 'authExpired']),
      onRehydrateStorage: () => (state) => {
        if (state) {
          const parsed = apiUserSchema.safeParse(state.user)
          state.user = parsed.success ? parsed.data : null
          state.hasHydrated = true
        } else {
          useUserStore.setState({ hasHydrated: true })
        }
      },
    }
  )
)

useUserStore.subscribe((state, prevState) => {
  const prevLang = (prevState.user?.language ?? 'fr').split('-')[0]
  const newLang = (state.user?.language ?? 'fr').split('-')[0]
  if (prevLang !== newLang || newLang !== i18n.language) {
    i18n.changeLanguage(newLang)
  }
})
