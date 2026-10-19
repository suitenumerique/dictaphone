// inspired byhttps://github.com/suitenumerique/drive/blob/c4188f8342ca7aa9096ea8d1aee6bc529d51809f/src/frontend/apps/drive/src/features/explorer/hooks/useUpload.tsx#L200

import { useMemo, useRef } from 'react'
import { Id, toast } from 'react-toastify'
import { useDropzone } from 'react-dropzone'
import { fromEvent, type FileWithPath } from 'file-selector'
import { COMMON_MIME_TYPES } from 'file-selector/mime'
import { useTranslation } from 'react-i18next'
import { addToast, ToasterItem } from '@/features/ui/components/toaster/Toaster'
import {
  enqueueImportUploads,
  useImportUploads,
} from '@/features/files/importUploads'
import { useConfig } from '@/api/useConfig.ts'
import prettyBytes from 'pretty-bytes'
import { getAudioDuration } from '@/features/recordings/utils/getAudioDuration.ts'
import { intervalToDuration } from 'date-fns'
import { useSettingsStore } from '@/features/settings/settingsStore'

export const useUploadZone = () => {
  const { t } = useTranslation('upload')
  const { data: appConfig } = useConfig()

  const fileDragToastId = useRef<Id | null>(null)
  const setUploadingState = useImportUploads.setState

  const allowedMimetypes = useMemo(
    () => appConfig?.audio_recording.allowed_mimetypes ?? [],
    [appConfig]
  )

  const allowedExtensions = useMemo(
    () => new Set(appConfig?.audio_recording.allowed_extensions ?? []),
    [appConfig]
  )
  const maxSize = useMemo(
    () => appConfig?.audio_recording.max_size ?? 0,
    [appConfig]
  )

  const accept = useMemo(
    () =>
      allowedMimetypes.reduce<Record<string, string[]>>((acc, mimetype) => {
        acc[mimetype] = []
        return acc
      }, {}),
    [allowedMimetypes]
  )

  const dismissDragToast = () => {
    if (!fileDragToastId.current) {
      return
    }
    toast.dismiss(fileDragToastId.current)
    fileDragToastId.current = null
  }

  const dropZone = useDropzone({
    accept,
    maxSize,
    getFilesFromEvent: (event) =>
      fromEvent(event, { mimeTypes: COMMON_MIME_TYPES }),
    noClick: true,
    useFsAccessApi: false,
    // If we do not set this, the click on the "..." menu of each items does not work, also click + select on items
    // does not work too. It might seems related to onFocus and onBlur events.
    noKeyboard: true,
    onDragEnter: () => {
      if (fileDragToastId.current) {
        return
      }

      fileDragToastId.current = addToast(
        <ToasterItem type={'info'} onDrop={dismissDragToast}>
          <span className="material-icons">cloud_upload</span>
          <span>{t(`uploader.toast`)}</span>
        </ToasterItem>,
        { autoClose: false }
      )
    },
    onDragLeave: (event) => {
      // Check if we're leaving the dropzone for a toast or staying within the dropzone area
      const relatedTarget = event.relatedTarget as Element
      const isToastElement = relatedTarget?.closest('.Toastify')

      /*  If we're leaving the dropzone for a toast, we don't need to dismiss the toast.
       *  This is useful to avoid the flicker effect when the user drops a file over the toast.
       *  However, if we drop over a toast, the toast is never closed. This is because we added the onDrop={handleDrop} on the ToasterItem.
       */
      if (isToastElement) {
        return
      }

      dismissDragToast()
    },
    onDrop: async (acceptedFiles, fileRejections) => {
      const selectedLanguage =
        useSettingsStore.getState().newTranscriptionLanguage ?? 'fr'
      dismissDragToast()

      for (const rejection of fileRejections) {
        let label = 'error'
        if (rejection.errors[0].code === 'file-invalid-type') {
          label = t('errors.unsupportedMimeType', {
            mimeType: rejection.file.name,
          })
        } else if (rejection.errors[0].code === 'file-too-large') {
          label = t('errors.tooLarge', {
            value: prettyBytes(maxSize),
          })
        }
        addToast(
          <ToasterItem type="error">
            <span>{label}</span>
          </ToasterItem>
        )
      }

      if (acceptedFiles.length === 0) {
        return
      }

      setUploadingState((prev) => ({
        ...prev,
        step: 'preparing',
      }))

      const validFiles: (FileWithPath & { durationSeconds: number })[] = []

      for (const acceptedFile of acceptedFiles) {
        // react-dropzone's callback now exposes File[], while file-selector adds
        // path metadata to every File it returns.
        const file = acceptedFile as unknown as FileWithPath
        const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`
        if (!allowedExtensions.has(extension)) {
          addToast(
            <ToasterItem type="error">
              <span>{t('errors.unsupportedExtension', { extension })}</span>
            </ToasterItem>
          )
          continue
        }

        const durationSeconds = await getAudioDuration(file)
        if (durationSeconds === null) {
          addToast(
            <ToasterItem type="error">
              <span>{t('errors.unrecognizedAudio')}</span>
            </ToasterItem>
          )
          continue
        }

        const maxAudioDurationSeconds =
          appConfig!.audio_recording.max_duration_seconds

        if (durationSeconds > maxAudioDurationSeconds) {
          addToast(
            <ToasterItem type="error">
              <span>
                {t('errors.tooLong', {
                  maxDuration: intervalToDuration({
                    start: 0,
                    end: maxAudioDurationSeconds * 1000,
                  }),
                  duration: intervalToDuration({
                    start: 0,
                    end: durationSeconds * 1000,
                  }),
                })}
              </span>
            </ToasterItem>
          )
          continue
        }

        ;(file as FileWithPath & { durationSeconds: number }).durationSeconds =
          durationSeconds
        validFiles.push(file as FileWithPath & { durationSeconds: number })
      }
      if (validFiles.length === 0) {
        setUploadingState({ step: 'done' })
        return
      }

      enqueueImportUploads(
        validFiles.map((file) => ({
          file,
          durationSeconds: file.durationSeconds,
        })),
        selectedLanguage
      )
    },
  })

  return {
    dropZone,
  }
}
