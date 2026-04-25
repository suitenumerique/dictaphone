import { createMMKV } from 'react-native-mmkv'
import {
  createJSONStorage,
  persist,
  type StateStorage,
} from 'zustand/middleware'
import { create } from 'zustand'
import { type LocalRecording, recordingSchema } from '../types/localRecording'
import { type AppSettings, appSettingsSchema } from '../types/settings'
import type { ApiUser } from '@/features/auth/api/ApiUser'
import { z } from 'zod/v4'
import NetInfo from '@react-native-community/netinfo'
import { createFile } from '@/features/files/api/createFile'
import { queryClient } from '@/api/queryClient'
import { keys } from '@/api/queryKeys'
import i18n from '@/i18n'

const storage = createMMKV({
  id: 'transcript-storage',
})

const defaultSettings: AppSettings = {
  language: 'en',
}

const apiUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  language: z.enum(['fr-fr', 'en-us']),
  timezone: z.string(),
})

const recordingListSchema = z.array(recordingSchema)

const mmkvStorage: StateStorage = {
  setItem: (name, value) => {
    storage.set(name, value)
  },
  getItem: (name) => {
    return storage.getString(name) ?? null
  },
  removeItem: (name) => {
    storage.remove(name)
  },
}

export interface RecordingsStore {
  hasHydrated: boolean
  recordings: LocalRecording[]
  addRecording: (recording: LocalRecording) => void
  deleteRecording: (recordingId: string) => void
  updateRecording: (
    id: string,
    data: Partial<Omit<LocalRecording, 'id'>>
  ) => void
}

export interface SettingsStore {
  hasHydrated: boolean
  settings: AppSettings
  setSettings: (settings: AppSettings) => void
  resetSettings: () => void
}

export interface UserStore {
  hasHydrated: boolean
  user: ApiUser | null
  authExpired: boolean
  setAuthExpired: (expired: boolean) => void
  setCachedUser: (user: ApiUser) => void
  clearCachedUser: () => void
}

const checkIsOnline = async (): Promise<boolean> => {
  const state = await NetInfo.fetch()
  return state.isConnected === true && state.isInternetReachable !== false
}

let isUploadInProgress = false
const triggerUpload = async (): Promise<void> => {
  if (isUploadInProgress) {
    return
  }

  const online = await checkIsOnline()
  if (!online) {
    return
  }

  const { recordings, updateRecording, deleteRecording } =
    useRecordingsStore.getState()
  const recordingToUpload =
    recordings.find((r) => r.uploadingStatus === 'to_upload') ?? null

  if (!recordingToUpload) {
    return
  }

  isUploadInProgress = true
  updateRecording(recordingToUpload.id, { uploadingStatus: 'uploading' })

  try {
    await createFile({
      durationSeconds: recordingToUpload.duration_seconds,
      createdAt: recordingToUpload.created_at,
      file: {
        name: `${recordingToUpload.title}.m4a`,
        type: 'audio/mp4',
        uri: recordingToUpload.filePath,
      },
    })
    deleteRecording(recordingToUpload.id)
    await queryClient.invalidateQueries({ queryKey: [keys.files] })
  } catch (error) {
    console.error('Error creating file:', error)
    updateRecording(recordingToUpload.id, { uploadingStatus: 'failed' })
  } finally {
    isUploadInProgress = false
    triggerUpload().catch(console.error)
  }
}

let isRecordingsUploadManagerStarted = false
const startRecordingsUploadManager = () => {
  if (isRecordingsUploadManagerStarted) {
    return
  }
  isRecordingsUploadManagerStarted = true

  useRecordingsStore.subscribe((state) => {
    if (state.recordings.some((r) => r.uploadingStatus === 'to_upload')) {
      triggerUpload().catch(console.error)
    }
  })

  NetInfo.addEventListener(() => {
    triggerUpload().catch(console.error)
  })

  triggerUpload().catch(console.error)
}

export const useRecordingsStore = create<RecordingsStore>()(
  persist(
    (set) => ({
      hasHydrated: false,
      recordings: [],
      addRecording: (recording) =>
        set((state) => ({ recordings: [recording, ...state.recordings] })),
      deleteRecording: (recordingId) =>
        set((state) => ({
          recordings: state.recordings.filter(
            (recording) => recording.id !== recordingId
          ),
        })),
      updateRecording: (id, data) =>
        set((state) => ({
          recordings: state.recordings.map((recording) =>
            recording.id === id ? { ...recording, ...data } : recording
          ),
        })),
    }),
    {
      name: 'recordings',
      storage: createJSONStorage(() => mmkvStorage),
      version: 1,
      onRehydrateStorage: () => (state) => {
        if (state) {
          const parsed = recordingListSchema.safeParse(state.recordings)
          state.recordings = parsed.success
            ? parsed.data.map((el) =>
                el.uploadingStatus === 'failed'
                  ? { ...el, uploadingStatus: 'to_upload' }
                  : el
              )
            : []
          state.hasHydrated = true
        }
      },
    }
  )
)

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      hasHydrated: false,
      settings: { ...defaultSettings },
      setSettings: (settings) => set({ settings }),
      resetSettings: () => set({ settings: defaultSettings }),
    }),
    {
      name: 'settings',
      storage: createJSONStorage(() => mmkvStorage),
      version: 1,
      onRehydrateStorage: () => (state) => {
        if (state) {
          const parsed = appSettingsSchema.safeParse(state.settings)
          state.settings = parsed.success ? parsed.data : { ...defaultSettings }
          state.hasHydrated = true
        }
      },
    }
  )
)

export const useUserStore = create<UserStore>()(
  persist(
    (set) => ({
      hasHydrated: false,
      user: null,
      authExpired: false,
      setAuthExpired: (expired) => set({ authExpired: expired }),
      setCachedUser: (user) => set({ user }),
      clearCachedUser: () => set({ user: null }),
    }),
    {
      name: 'user-info',
      storage: createJSONStorage(() => mmkvStorage),
      version: 1,
      onRehydrateStorage: () => (state) => {
        if (state) {
          const parsed = apiUserSchema.safeParse(state.user)
          state.user = parsed.success ? parsed.data : null
          state.hasHydrated = true
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

startRecordingsUploadManager()
