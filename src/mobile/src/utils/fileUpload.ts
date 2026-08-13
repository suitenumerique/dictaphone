import {
  NativeEventEmitter,
  NativeModules,
  PermissionsAndroid,
  Platform,
} from 'react-native'
import { toByteArray } from 'react-native-quick-base64'
import i18n from '@/i18n'

export type NativeUploadStatus = {
  uploadId: string
  status: 'uploading' | 'uploadedAwaitingFinalize' | 'failed'
  uploadedBytes: number
  totalBytes: number
  error?: string
}

type NativeUploadProgress = {
  uploadId: string
  uploadedBytes: number
  totalBytes: number
  progress: number
}

export type UploadNotificationStrings = {
  channelName: string
  uploadingTitle: string
  uploadingIndeterminate: string
  completeTitle: string
  completeBody: string
  failedTitle: string
  failedBody: string
}

type FileUploadNativeModule = {
  addListener: (eventName: string) => void
  removeListeners: (count: number) => void
  uploadFile: (
    filePath: string,
    url: string,
    contentType: string,
    uploadId: string,
    wifiOnly: boolean,
    notificationStrings: UploadNotificationStrings
  ) => Promise<void>
  getUploadStatuses: () => Promise<NativeUploadStatus[]>
  resumeUpload: (
    uploadId: string,
    notificationStrings: UploadNotificationStrings
  ) => Promise<void>
  waitForUpload: (uploadId: string) => Promise<void>
  markUploadFinalized: (uploadId: string) => Promise<void>
  clearUpload: (uploadId: string) => Promise<void>
  setAppActive: (active: boolean) => void
  requestNotificationPermission?: () => Promise<boolean>
  readBundledFileAsBase64?: (fileName: string) => Promise<string>
  copyExternalFile?: (
    sourceUri: string,
    fileName: string,
    maxSize: number
  ) => Promise<{ path: string; name: string; size: number }>
}

const { FileUploadModule } = NativeModules as {
  FileUploadModule?: FileUploadNativeModule
}

const uploadProgressEvent = 'FileUploadProgress'
export const incomingSharedFileEvent = 'IncomingSharedFile'

export type UploadProgress = {
  uploadedBytes: number
  totalBytes: number
  progress: number
  percentage: number
}

export type UploadProgressCallback = (progress: UploadProgress) => void

export const createUploadId = () =>
  `${Date.now()}-${Math.random().toString(36).slice(2)}`

const getUploadNotificationStrings = (): UploadNotificationStrings => ({
  channelName: i18n.t('recordings.uploadNotifications.channelName'),
  uploadingTitle: i18n.t('recordings.uploadNotifications.uploadingTitle'),
  uploadingIndeterminate: i18n.t(
    'recordings.uploadNotifications.uploadingIndeterminate'
  ),
  completeTitle: i18n.t('recordings.uploadNotifications.completeTitle'),
  completeBody: i18n.t('recordings.uploadNotifications.completeBody'),
  failedTitle: i18n.t('recordings.uploadNotifications.failedTitle'),
  failedBody: i18n.t('recordings.uploadNotifications.failedBody'),
})

let notificationPermissionRequested = false

export const requestUploadNotificationPermission = async (): Promise<void> => {
  if (notificationPermissionRequested) {
    return
  }

  if (Platform.OS === 'android' && Number(Platform.Version) >= 33) {
    await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS
    )
  } else {
    await FileUploadModule?.requestNotificationPermission?.()
  }
  notificationPermissionRequested = true
}

export const setFileUploadAppActive = (active: boolean): void => {
  FileUploadModule?.setAppActive(active)
}

export const uploadFileToS3 = async (
  fileUri: string,
  presignedUrl: string,
  contentType: string,
  onProgress?: UploadProgressCallback,
  uploadId = createUploadId(),
  wifiOnly = false
): Promise<void> => {
  if (!FileUploadModule) {
    throw new Error('FileUploadModule is not available')
  }

  const filePath = fileUri.replace('file://', '')
  const notificationStrings = getUploadNotificationStrings()
  const eventEmitter = onProgress
    ? new NativeEventEmitter(FileUploadModule)
    : null
  const subscription = eventEmitter?.addListener(
    uploadProgressEvent,
    (event: NativeUploadProgress) => {
      if (event.uploadId !== uploadId) {
        return
      }

      onProgress?.({
        uploadedBytes: event.uploadedBytes,
        totalBytes: event.totalBytes,
        progress: event.progress,
        percentage: event.progress * 100,
      })
    }
  )

  try {
    await FileUploadModule.uploadFile(
      filePath,
      presignedUrl,
      contentType,
      uploadId,
      wifiOnly,
      notificationStrings
    )
  } finally {
    subscription?.remove()
  }
}

export const getUploadStatuses = async (): Promise<NativeUploadStatus[]> => {
  if (!FileUploadModule) {
    throw new Error('FileUploadModule is not available')
  }
  return FileUploadModule.getUploadStatuses()
}

export const resumeUpload = async (uploadId: string): Promise<void> => {
  if (!FileUploadModule) {
    throw new Error('FileUploadModule is not available')
  }
  return FileUploadModule.resumeUpload(uploadId, getUploadNotificationStrings())
}

export const waitForUpload = async (uploadId: string): Promise<void> => {
  if (!FileUploadModule) {
    throw new Error('FileUploadModule is not available')
  }
  return FileUploadModule.waitForUpload(uploadId)
}

export const markUploadFinalized = async (uploadId: string): Promise<void> => {
  if (!FileUploadModule) {
    throw new Error('FileUploadModule is not available')
  }
  return FileUploadModule.markUploadFinalized(uploadId)
}

export const clearUpload = async (uploadId: string): Promise<void> => {
  if (!FileUploadModule) {
    throw new Error('FileUploadModule is not available')
  }
  return FileUploadModule.clearUpload(uploadId)
}

export const readBundledFileAsArrayBuffer = async (
  fileName: string
): Promise<ArrayBuffer> => {
  if (!FileUploadModule?.readBundledFileAsBase64) {
    throw new Error('FileUploadModule.readBundledFileAsBase64 is not available')
  }

  const base64Payload = await FileUploadModule.readBundledFileAsBase64(fileName)
  return new Uint8Array(toByteArray(base64Payload, true)).buffer
}

export type ExternalFileCopy = {
  path: string
  name: string
  size: number
}

export const copyExternalFile = async (
  sourceUri: string,
  fileName: string,
  maxSize = 0
): Promise<ExternalFileCopy> => {
  if (!FileUploadModule?.copyExternalFile) {
    throw new Error('FileUploadModule.copyExternalFile is not available')
  }

  return FileUploadModule.copyExternalFile(sourceUri, fileName, maxSize)
}
