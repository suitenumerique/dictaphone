import { NativeModules } from 'react-native'

export type LocalDocumentM4AFile = {
  path: string
  name: string
  createdAtMs: number
  durationSeconds: number
  fileSizeBytes: number
}

const { FileUploadModule } = NativeModules as {
  FileUploadModule?: {
    deleteLocalFile?: (filePath: string) => Promise<void>
    localFileExists?: (filePath: string) => Promise<boolean>
    listDocumentM4AFiles?: () => Promise<LocalDocumentM4AFile[]>
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

export const listDocumentM4AFiles = async (): Promise<
  LocalDocumentM4AFile[]
> => {
  if (!FileUploadModule?.listDocumentM4AFiles) {
    throw new Error('Document m4a listing is not available')
  }

  return FileUploadModule.listDocumentM4AFiles()
}
