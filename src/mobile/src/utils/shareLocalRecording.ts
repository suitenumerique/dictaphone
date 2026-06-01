import { NativeModules } from 'react-native'

const { FileUploadModule } = NativeModules as {
  FileUploadModule?: {
    shareAudioFile?: (filePath: string, fileName: string) => Promise<void>
  }
}

const normalizeFilePath = (filePath: string) =>
  filePath.startsWith('file://') ? filePath.slice('file://'.length) : filePath

export const shareLocalRecording = async (
  filePath: string,
  fileName: string
): Promise<void> => {
  if (!FileUploadModule?.shareAudioFile) {
    throw new Error('File sharing is not available')
  }

  await FileUploadModule.shareAudioFile(normalizeFilePath(filePath), fileName)
}
