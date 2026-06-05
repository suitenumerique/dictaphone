import { NativeModules } from 'react-native'

const { FileUploadModule } = NativeModules as {
  FileUploadModule?: {
    deleteLocalFile?: (filePath: string) => Promise<void>
    localFileExists?: (filePath: string) => Promise<boolean>
  }
}

export const localRecordingFileExists = async (
  filePath: string
): Promise<boolean> => {
  if (!FileUploadModule?.localFileExists) {
    throw new Error('Local file existence check is not available')
  }

  return FileUploadModule.localFileExists(filePath)
}

export const deleteLocalRecordingFile = async (
  filePath: string
): Promise<void> => {
  if (!FileUploadModule?.deleteLocalFile) {
    throw new Error('Local file deletion is not available')
  }

  await FileUploadModule.deleteLocalFile(filePath)
}
