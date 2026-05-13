import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { z } from 'zod/v4'
import { mmkvStorage } from '@/services/index'

export const DEFAULT_MAX_RECORDING_DURATION_SECONDS = 60 * 60 * 3

const apiConfigSchema = z.object({
  analytics: z
    .object({
      id: z.string(),
      host: z.string(),
    })
    .optional(),
  audio_recording: z.object({
    upload_is_enabled: z.boolean(),
    max_size: z.number(),
    max_duration_seconds: z.number(),
    max_count_by_user: z.number(),
    allowed_extensions: z.array(z.string()),
    allowed_mimetypes: z.array(z.string()),
  }),
  mobile_app: z.object({
    ios_download_link: z.string(),
    android_download_link: z.string(),
    ios_version: z.string(),
    ios_min_version: z.string(),
    android_version: z.string(),
    android_min_version: z.string(),
  }),
})

type ConfigStoreSchema = z.infer<typeof apiConfigSchema>

export interface ConfigStore {
  hasHydrated: boolean
  config: ConfigStoreSchema | null
  setCachedConfig: (config: ConfigStoreSchema) => void
  clearCachedConfig: () => void
  maxDurationSeconds: number
}

export const useConfigStore = create<ConfigStore>()(
  persist(
    (set) => ({
      hasHydrated: false,
      config: null,
      setCachedConfig: (config) =>
        set({
          config,
          maxDurationSeconds: config.audio_recording.max_duration_seconds,
        }),
      clearCachedConfig: () => set({ config: null }),
      maxDurationSeconds: DEFAULT_MAX_RECORDING_DURATION_SECONDS,
    }),
    {
      name: 'config',
      storage: createJSONStorage(() => mmkvStorage),
      version: 1,
      onRehydrateStorage: () => (state) => {
        if (state) {
          const parsed = apiConfigSchema.safeParse(state.config)
          state.config = parsed.success ? parsed.data : null
          state.maxDurationSeconds =
            state.config?.audio_recording?.max_duration_seconds ??
            DEFAULT_MAX_RECORDING_DURATION_SECONDS
        }
        useConfigStore.setState({ hasHydrated: true })
      },
    }
  )
)
