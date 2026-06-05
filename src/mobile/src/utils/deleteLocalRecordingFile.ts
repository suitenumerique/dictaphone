import { NativeModules } from 'react-native'

const { FileUploadModule } = NativeModules as {
  FileUploadModule?: {
    deleteLocalFile?: (filePath: string) => Promise<void>
  }
}

export const deleteLocalRecordingFile = async (
  filePath: string
): Promise<void> => {
  if (!FileUploadModule?.deleteLocalFile) {
    throw new Error('Local file deletion is not available')
  }

  await FileUploadModule.deleteLocalFile(filePath)
}
