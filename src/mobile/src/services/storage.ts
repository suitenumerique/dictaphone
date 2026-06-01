import { createJSONStorage, persist } from 'zustand/middleware'
import { create } from 'zustand'
import { type LocalRecording, recordingSchema } from '../types/localRecording'
import { type AppSettings, appSettingsSchema } from '../types/settings'
import { z } from 'zod/v4'
import NetInfo from '@react-native-community/netinfo'
import { createFile } from '@/features/files/api/createFile'
import { queryClient } from '@/api/queryClient'
import { keys } from '@/api/queryKeys'
import { mmkvStorage } from '@/services/index'
import omit from '@/utils/omit'
import { useUserStore } from '@/services/userStore'

const defaultSettings: AppSettings = {
  language: 'en',
  wifiOnlyUpload: true,
}

const recordingListSchema = z.array(recordingSchema)

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

export interface UploadStore {
  bypassWifiOnly: boolean
  setBypassWifiOnly: (value: boolean) => void
}

const checkCanUpload = async (): Promise<boolean> => {
  let state
  try {
    state = await NetInfo.fetch()
  } catch (error) {
    console.error('Failed to fetch network state:', error)
    return false
  }
  if (state.isConnected !== true || state.isInternetReachable === false) {
    return false
  }
  const { settings } = useSettingsStore.getState()
  const { bypassWifiOnly } = useUploadStore.getState()
  if (settings.wifiOnlyUpload && !bypassWifiOnly) {
    return state.type === 'wifi'
  }
  return true
}

let isUploadInProgress = false
const triggerUpload = async (): Promise<void> => {
  if (isUploadInProgress) {
    return
  }

  const { user, authExpired } = useUserStore.getState()
  if (!user || authExpired) {
    return
  }

  const canUpload = await checkCanUpload()
  if (!canUpload) {
    return
  }

  const { recordings, updateRecording, deleteRecording } =
    useRecordingsStore.getState()
  const recordingToUpload =
    recordings.find((r) => r.uploadingStatus === 'to_upload') ?? null

  if (!recordingToUpload) {
    // reset bypass wifiOnly
    setBypassWifiOnly(false)
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
      onProgress: (progress) => {
        updateRecording(recordingToUpload.id, {
          uploadProgress: progress,
        })
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

export const setBypassWifiOnly = (value: boolean) => {
  useUploadStore.getState().setBypassWifiOnly(value)
  if (value) {
    triggerUpload().catch(console.error)
  }
}

let isRecordingsUploadManagerStarted = false
const startRecordingsUploadManager = () => {
  console.log('Start recordings upload manager')
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
      partialize: (state) => omit(state, ['hasHydrated']),
      onRehydrateStorage: () => (state) => {
        if (state) {
          const parsed = recordingListSchema.safeParse(state.recordings)
          state.recordings = parsed.success
            ? // we force all files back to "to_upload" status
              parsed.data.map((el) => ({
                ...el,
                uploadingStatus: 'to_upload',
                uploadPercentage: undefined,
              }))
            : []
          state.hasHydrated = true
        } else {
          useRecordingsStore.setState({ hasHydrated: true })
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
      partialize: (state) => omit(state, ['hasHydrated']),
      onRehydrateStorage: () => (state) => {
        if (state) {
          const parsed = appSettingsSchema.safeParse(state.settings)
          state.settings = parsed.success ? parsed.data : { ...defaultSettings }
          state.hasHydrated = true
        } else {
          useSettingsStore.setState({ hasHydrated: true })
        }
      },
    }
  )
)

export const useUploadStore = create<UploadStore>()((set) => ({
  bypassWifiOnly: false,
  setBypassWifiOnly: (value) => set({ bypassWifiOnly: value }),
}))

startRecordingsUploadManager()

useUserStore.subscribe((newState, oldState) => {
  if (newState.user && !oldState.user) {
    triggerUpload().catch(console.error)
  }
  if (!newState.authExpired && oldState.authExpired) {
    const { recordings, updateRecording } = useRecordingsStore.getState()
    recordings
      .filter((recording) => recording.uploadingStatus === 'failed')
      .forEach((recording) => {
        updateRecording(recording.id, {
          uploadingStatus: 'to_upload',
          uploadProgress: undefined,
        })
      })
    triggerUpload().catch(console.error)
  }
})
