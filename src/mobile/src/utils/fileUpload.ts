import { NativeEventEmitter, NativeModules } from 'react-native'
import { toByteArray } from 'react-native-quick-base64'

type FileUploadNativeModule = {
  addListener: (eventName: string) => void
  removeListeners: (count: number) => void
  uploadFile: (
    filePath: string,
    url: string,
    contentType: string,
    uploadId: string
  ) => Promise<void>
  readBundledFileAsBase64?: (fileName: string) => Promise<string>
}

const { FileUploadModule } = NativeModules as {
  FileUploadModule?: FileUploadNativeModule
}
const uploadProgressEvent = 'FileUploadProgress'

type NativeUploadProgress = {
  uploadId: string
  uploadedBytes: number
  totalBytes: number
  progress: number
}

export type UploadProgress = {
  uploadedBytes: number
  totalBytes: number
  progress: number
  percentage: number
}

export type UploadProgressCallback = (progress: UploadProgress) => void

const createUploadId = () =>
  `${Date.now()}-${Math.random().toString(36).slice(2)}`

export const uploadFileToS3 = async (
  fileUri: string,
  presignedUrl: string,
  contentType: string,
  onProgress?: UploadProgressCallback
): Promise<void> => {
  if (!FileUploadModule) {
    throw new Error('FileUploadModule is not available')
  }

  // Strip file:// prefix — the native layer handles it
  const filePath = fileUri.replace('file://', '')
  const uploadId = createUploadId()
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
      uploadId
    )
  } finally {
    subscription?.remove()
  }
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
