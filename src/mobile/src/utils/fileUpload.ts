import { NativeEventEmitter, NativeModules } from 'react-native'

const { FileUploadModule } = NativeModules
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
