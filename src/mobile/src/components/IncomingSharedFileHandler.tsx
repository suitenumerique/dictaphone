import { useCallback, useEffect, useRef } from 'react'
import { Alert, Linking, NativeEventEmitter, NativeModules } from 'react-native'
import { useTranslation } from 'react-i18next'
import { useConfig } from '@/api/useConfig'
import {
  ImportedFileError,
  queueImportedFile,
  type ImportedFileInput,
} from '@/services/importedFile'
import { incomingSharedFileEvent } from '@/utils/fileUpload'

type IncomingSharedFile = {
  uri: string
  name?: string | null
  type?: string | null
}

const isFileUrl = (url: string) =>
  url.startsWith('file://') || url.startsWith('content://')

const fileNameFromUrl = (url: string): string | null => {
  try {
    const path = decodeURIComponent(url.split('?')[0])
    const name = path.split('/').pop()
    return name || null
  } catch {
    return null
  }
}

const importErrorMessage = (
  t: ReturnType<typeof useTranslation>['t'],
  code: string
) => {
  switch (code) {
    case 'unsupported_type':
      return t('recordings.import.errors.unsupported_type')
    case 'too_large':
      return t('recordings.import.errors.too_large')
    case 'too_long':
      return t('recordings.import.errors.too_long')
    case 'unrecognized_audio':
      return t('recordings.import.errors.unrecognized_audio')
    default:
      return t('recordings.import.errors.generic')
  }
}

export function IncomingSharedFileHandler() {
  const { t } = useTranslation()
  const configQuery = useConfig()
  const pendingFiles = useRef<ImportedFileInput[]>([])
  const processedUris = useRef(new Set<string>())

  const processFile = useCallback(
    async (file: ImportedFileInput) => {
      if (processedUris.current.has(file.uri)) {
        return
      }
      if (!configQuery.data) {
        pendingFiles.current.push(file)
        return
      }

      processedUris.current.add(file.uri)
      try {
        await queueImportedFile(file)
      } catch (error) {
        processedUris.current.delete(file.uri)
        const code = error instanceof ImportedFileError ? error.code : 'generic'
        Alert.alert(
          t('recordings.import.errorTitle'),
          importErrorMessage(t, code)
        )
      }
    },
    [configQuery.data, t]
  )

  useEffect(() => {
    if (!configQuery.data || pendingFiles.current.length === 0) {
      return
    }
    const filesToProcess = [...pendingFiles.current]
    pendingFiles.current = []
    filesToProcess.forEach((file) => {
      void processFile(file)
    })
  }, [configQuery.data, processFile])

  useEffect(() => {
    const nativeModule = NativeModules.FileUploadModule as {
      addListener: (eventName: string) => void
      removeListeners: (count: number) => void
      getPendingSharedFile?: () => Promise<
        IncomingSharedFile[] | IncomingSharedFile | null
      >
    }
    const subscriptions: { remove: () => void }[] = []
    const nativeEmitter = new NativeEventEmitter(nativeModule)

    const onIncomingFile = (file: IncomingSharedFile) => {
      if (!file?.uri) {
        return
      }
      void processFile({
        uri: file.uri,
        name: file.name,
        type: file.type,
      })
    }

    subscriptions.push(
      nativeEmitter.addListener(incomingSharedFileEvent, onIncomingFile)
    )

    void nativeModule.getPendingSharedFile?.().then((result) => {
      if (!result) {
        return
      }
      const files = Array.isArray(result) ? result : [result]
      files.forEach((file) => {
        if (file) {
          onIncomingFile(file)
        }
      })
    })

    void Linking.getInitialURL().then((url) => {
      if (url && isFileUrl(url)) {
        onIncomingFile({ uri: url, name: fileNameFromUrl(url) })
      }
    })

    subscriptions.push(
      Linking.addEventListener('url', ({ url }) => {
        if (isFileUrl(url)) {
          onIncomingFile({ uri: url, name: fileNameFromUrl(url) })
        }
      })
    )

    return () => subscriptions.forEach((subscription) => subscription.remove())
  }, [processFile])

  return null
}
