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
import {
  deleteLocalRecordingFile,
  getFileName,
  listDocumentM4AFiles,
  LocalDocumentM4AFile,
  localRecordingFileExists,
} from '@/utils/localRecordingFile'
import i18n from '@/i18n'
import { type TTranscriptionLanguage } from '@/features/ai-jobs/api/types'
import {
  concatSubAudioFiles,
  FILENAME_PREFIX_SEPARATOR,
} from '@/features/recordings/utils/concatSubAudioFiles'
import uuid from 'react-native-uuid'
import { wait } from '@/utils/wait'

const defaultSettings: AppSettings = {
  language: 'en',
  wifiOnlyUpload: true,
}

const recordingListSchema = z.array(recordingSchema)

const removeMissingLocalRecordingsAfterHydration = async (
  recordings: LocalRecording[]
): Promise<void> => {
  const missingRecordings: LocalRecording[] = []

  for (const recording of recordings) {
    try {
      const fileExists = await localRecordingFileExists(recording.filePath)
      if (!fileExists) {
        missingRecordings.push(recording)
      }
    } catch (error) {
      console.error(
        `Failed to check local recording file for id "${recording.id}":`,
        error
      )
    }
  }

  if (missingRecordings.length === 0) {
    return
  }

  const missingRecordingIdsSet = new Set(
    missingRecordings.map((recording) => recording.id)
  )
  const removedFileList = missingRecordings
    .map((recording) => {
      const trimmedTitle = recording.title.trim()
      return `• ${
        trimmedTitle.length > 0
          ? trimmedTitle
          : i18n.t('recordings.missingFiles.untitledFallback')
      }`
    })
    .join('\n')

  useRecordingsStore.setState((state) => ({
    recordings: state.recordings.filter(
      (recording) => !missingRecordingIdsSet.has(recording.id)
    ),
    missingFilesPending: state.missingFilesPending
      ? `${state.missingFilesPending}\n${removedFileList}`
      : removedFileList,
  }))
}

export type TRecoverFilesStatus =
  | { status: 'to_run' }
  | { status: 'init' }
  | { status: 'running' }
  | { status: 'done'; recovered: string[] }

export interface RecordingsStore {
  hasHydrated: boolean
  recordings: LocalRecording[]
  missingFilesPending: string | null
  recoverFilesStatus: TRecoverFilesStatus
  addRecording: (recording: LocalRecording) => void
  deleteRecording: (recordingId: string) => Promise<void>
  updateRecording: (
    id: string,
    data: Partial<Omit<LocalRecording, 'id'>>
  ) => void
}

export interface SettingsStore {
  hasHydrated: boolean
  settings: AppSettings
  newTranscriptionLanguage: TTranscriptionLanguage | null
  androidBatteryWarningShown: boolean
  setSettings: (settings: AppSettings) => void
  setNewTranscriptionLanguage: (language: TTranscriptionLanguage) => void
  setAndroidBatteryWarningShown: (shown: boolean) => void
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
      source: 'mobile_recording',
      language: recordingToUpload.language,
      onProgress: (progress) => {
        updateRecording(recordingToUpload.id, {
          uploadProgress: progress,
        })
      },
    })
    await deleteRecording(recordingToUpload.id)
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
export const startRecordingsUploadManager = () => {
  console.info('Start recordings upload manager')
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
    (set, get) => ({
      hasHydrated: false,
      recordings: [],
      missingFilesPending: null,
      recoverFilesStatus: { status: 'to_run' },
      addRecording: (recording) =>
        set((state) => ({ recordings: [recording, ...state.recordings] })),
      deleteRecording: async (recordingId) => {
        const recording = get().recordings.find(
          (item) => item.id === recordingId
        )
        if (recording) {
          deleteLocalRecordingFile(recording.filePath).catch((error) => {
            console.error(
              `Failed to delete local recording file for id "${recordingId}":`,
              error
            )
          })
        }
        set((state) => ({
          recordings: state.recordings.filter(
            (stateRecording) => stateRecording.id !== recordingId
          ),
        }))
      },
      updateRecording: (id, data) =>
        set((state) => ({
          recordings: state.recordings.map((recording) =>
            recording.id === id ? { ...recording, ...data } : recording
          ),
        })),
      clearMissingFilesPending: () => set({ missingFilesPending: null }),
    }),
    {
      name: 'recordings',
      storage: createJSONStorage(() => mmkvStorage),
      version: 1,
      partialize: (state) =>
        omit(state, [
          'hasHydrated',
          'missingFilesPending',
          'recoverFilesStatus',
        ]),
      onRehydrateStorage: () => (state) => {
        if (state) {
          const parsed = recordingListSchema.safeParse(state.recordings)
          state.recordings = parsed.success
            ? // we force all files back to "to_upload" status
              parsed.data.map((el) => ({
                ...el,
                uploadingStatus: 'to_upload',
                uploadProgress: undefined,
              }))
            : []
          state.recoverFilesStatus = { status: 'to_run' }
          state.hasHydrated = true

          removeMissingLocalRecordingsAfterHydration(state.recordings).catch(
            (error) => {
              console.error(
                'Failed to cleanup missing local recordings after rehydration:',
                error
              )
            }
          )
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
      newTranscriptionLanguage: null,
      androidBatteryWarningShown: false,
      setSettings: (settings) => set({ settings }),
      setNewTranscriptionLanguage: (newTranscriptionLanguage) =>
        set({ newTranscriptionLanguage }),
      setAndroidBatteryWarningShown: (androidBatteryWarningShown) =>
        set({ androidBatteryWarningShown }),
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
          state.newTranscriptionLanguage =
            state.newTranscriptionLanguage ?? 'fr'
          state.hasHydrated = true
          state.androidBatteryWarningShown =
            state.androidBatteryWarningShown ?? false
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

type TRecoverableFiles = Map<
  string,
  [LocalDocumentM4AFile, ...LocalDocumentM4AFile[]]
>

const appStartTime = Date.now()

const getFilesToRecover = async (): Promise<TRecoverableFiles> => {
  let localM4AFiles = await listDocumentM4AFiles()
  if (localM4AFiles.length === 0) {
    console.info(
      'No local M4A files found, waiting 1 second to double check in case of race condition'
    )
    await wait(1000)
    localM4AFiles = await listDocumentM4AFiles()
  }
  console.info('localM4AFiles', localM4AFiles)
  const rotatedFilesByFile: TRecoverableFiles = new Map()
  // We make sure not to include files that were created after the start of the app to avoid
  // including new recordings if the list takes time to create
  localM4AFiles = localM4AFiles.filter((el) => el.createdAtMs < appStartTime)

  localM4AFiles.forEach((file) => {
    const [fileId] = file.name.split(FILENAME_PREFIX_SEPARATOR)
    const existingFiles = rotatedFilesByFile.get(fileId)
    if (existingFiles) {
      existingFiles.push(file)
    } else {
      rotatedFilesByFile.set(fileId, [file])
    }
  })

  const knownRecordings = useRecordingsStore.getState().recordings
  const storedFileNamesSet = new Set(
    knownRecordings.map((recording) =>
      getFileName(recording.filePath).toLowerCase()
    )
  )

  // We remove files that are already in the recordings list
  for (const [key, files] of rotatedFilesByFile) {
    if (
      files.length === 1 &&
      storedFileNamesSet.has(getFileName(files[0].path))
    ) {
      rotatedFilesByFile.delete(key)
    }
  }

  return rotatedFilesByFile
}

const recoverFile = async (
  subFiles: [LocalDocumentM4AFile, ...LocalDocumentM4AFile[]]
): Promise<string | null> => {
  const recoveryLanguage: TTranscriptionLanguage =
    i18n.language === 'en' ? 'en' : 'fr'

  // We assume that the subfiles are sequentially ordered according to their name
  subFiles.sort((a, b) => a.name.localeCompare(b.name))
  const [concatenatedPath, usedSubFiles] = await concatSubAudioFiles(subFiles)
  if (concatenatedPath === null) {
    console.error('Failed to concatenate the audio files')
    return null
  }

  const createdAtDate =
    subFiles[0].createdAtMs > 0 ? new Date(subFiles[0].createdAtMs) : new Date()
  const title = `${i18n.t('home.recordingPrefix')} ${i18n.t(
    'shared.utils.formatDateTimeStatic',
    { value: createdAtDate }
  )}`

  useRecordingsStore.getState().addRecording({
    created_at: createdAtDate.toISOString(),
    duration_seconds: usedSubFiles.reduce(
      (acc, file) => acc + file.durationSeconds,
      0
    ),
    filePath: concatenatedPath,
    title,
    id: uuid.v4().toString(),
    language: recoveryLanguage,
    uploadingStatus: 'to_upload' as const,
  })
  return title
}

const recoverFiles = async (
  orphanedFiles: TRecoverableFiles
): Promise<string[]> => {
  const recovered = []

  for (const [, subFiles] of orphanedFiles) {
    try {
      const recoveredTitle = await recoverFile(subFiles)
      if (recoveredTitle === null) {
        console.error('Failed to recover file, skipping, deleted. ', subFiles)
        continue
      }
      recovered.push(recoveredTitle)
    } catch (e) {
      console.error(
        `Failed to recover file, skipping. ${JSON.stringify(subFiles)}`,
        e
      )
    }
  }

  return recovered
}

let restoreCheckHasRun = false
export const runRecovery = async (state?: RecordingsStore) => {
  if (!state) {
    state = useRecordingsStore.getState()
  }

  if (restoreCheckHasRun) return
  if (!state.hasHydrated) return
  console.info('Running recovery')

  restoreCheckHasRun = true
  useRecordingsStore.setState({
    recoverFilesStatus: { status: 'init' } satisfies TRecoverFilesStatus,
  })
  const orphanFiles = await getFilesToRecover()
  if (orphanFiles.size > 0) {
    console.info('Orphan files detected', orphanFiles)
    useRecordingsStore.setState({
      recoverFilesStatus: { status: 'running' } satisfies TRecoverFilesStatus,
    })
    const recovered = await recoverFiles(orphanFiles)
    useRecordingsStore.setState({
      recoverFilesStatus: {
        status: 'done',
        recovered,
      } satisfies TRecoverFilesStatus,
    })
  } else {
    console.info('No orphan files detected')
    useRecordingsStore.setState({
      recoverFilesStatus: {
        status: 'done',
        recovered: [],
      } satisfies TRecoverFilesStatus,
    })
  }
}

useRecordingsStore.subscribe(runRecovery)
