import { NativeModules } from 'react-native'

const { FileUploadModule } = NativeModules

export const uploadFileToS3 = async (
  fileUri: string,
  presignedUrl: string,
  contentType: string
): Promise<void> => {
  if (!FileUploadModule) {
    throw new Error('FileUploadModule is not available')
  }

  // Strip file:// prefix — the native layer handles it
  const filePath = fileUri.replace('file://', '')

  await FileUploadModule.uploadFile(filePath, presignedUrl, contentType)
}
