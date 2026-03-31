// inspired byhttps://github.com/suitenumerique/drive/blob/c4188f8342ca7aa9096ea8d1aee6bc529d51809f/src/frontend/apps/drive/src/features/explorer/hooks/useUpload.tsx#L200

import { useEffect, useMemo, useRef, useState } from 'react'
import { Id, toast } from 'react-toastify'
import { FileWithPath, useDropzone } from 'react-dropzone'
import { useTranslation } from 'react-i18next'
import { addToast, ToasterItem } from '@/features/ui/components/toaster/Toaster'
import { useCreateFile } from '@/features/files/api/createFile.ts'
import { FileUploadToast } from '@/features/files/components/FileUploadToast.tsx'
import { useConfig } from '@/api/useConfig.ts'
import prettyBytes from 'pretty-bytes'
import { getAudioDuration } from '@/features/recordings/utils/getAudioDuration.ts'
import { intervalToDuration } from 'date-fns'

export type FileUploadMeta = {
  file: File
  progress: number
  status: 'uploading' | 'done' | 'error'
}

enum UploadingStep {
  NONE = 'none',
  PREPARING = 'preparing',
  UPLOAD_FILES = 'upload_files',
  DONE = 'done',
}

export type UploadingState = {
  step: UploadingStep
  filesMeta: Record<string, FileUploadMeta>
}

/**
 * This function removes the leading "./" or "/" from the path.
 */
const pathNicefy = (path: string) => {
  return path.replace(/^[./]+/, '')
}

// 3 hours
const MAX_DURATION_SECONDS = 60 * 60 * 3

export const useUploadZone = () => {
  const { t } = useTranslation('upload')
  const { data: appConfig } = useConfig()

  const createFile = useCreateFile()

  const fileDragToastId = useRef<Id | null>(null)
  const fileUploadsToastId = useRef<Id | null>(null)
  const [uploadingState, setUploadingState] = useState<UploadingState>({
    step: UploadingStep.NONE,
    filesMeta: {},
  })

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
        step: UploadingStep.PREPARING,
      }))

      if (!fileUploadsToastId.current) {
        fileUploadsToastId.current = addToast(
          <FileUploadToast uploadingState={uploadingState} />,
          {
            autoClose: false,
            onClose: () => {
              // We need to set this to null in order to re-show the toast when the user drops another file later.
              fileUploadsToastId.current = null
            },
          }
        )
      }

      const validFiles: (FileWithPath & { durationSeconds: number })[] = []

      for (const file of acceptedFiles as FileWithPath[]) {
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
        if (
          durationSeconds === null ||
          durationSeconds > MAX_DURATION_SECONDS
        ) {
          addToast(
            <ToasterItem type="error">
              <span>
                {t('errors.tooLong', {
                  maxDuration: intervalToDuration({
                    start: 0,
                    end: MAX_DURATION_SECONDS * 1000,
                  }),
                  duration: intervalToDuration({
                    start: 0,
                    end: (durationSeconds ?? 0) * 1000,
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
        return
      }

      // Do not run "setUploadingState({});" because if a uploading is still in progress, it will be overwritten.

      // First, add all the files to the uploading state in order to display them in the toast.
      const newUploadingState: UploadingState = {
        step: UploadingStep.UPLOAD_FILES,
        filesMeta: {},
      }
      for (const file of validFiles) {
        newUploadingState.filesMeta[pathNicefy(file.path!)] = {
          file,
          progress: 0,
          status: 'uploading',
        }
      }
      setUploadingState(newUploadingState)

      // Then, upload all the files sequentially. We are not uploading them in parallel because the backend
      // does not support it, it causes concurrency issues.
      const promises = []
      for (const file of validFiles) {
        // We do not using "createFile.mutateAsync" because it causes unhandled errors.
        // Instead, we use a promise that we can await to run all the uploads sequentially.
        // Using "createFile.mutate" makes the error handled by the mutation hook itself.
        promises.push(
          () =>
            new Promise<void>((resolve) => {
              createFile.mutate(
                {
                  file,
                  durationSeconds: file.durationSeconds,
                  onProgress: (progress) => {
                    setUploadingState((prev) => {
                      return {
                        ...prev,
                        filesMeta: {
                          ...prev.filesMeta,
                          [pathNicefy(file.path!)]: {
                            file,
                            progress,
                            status: progress >= 100 ? 'done' : 'uploading',
                          },
                        },
                      }
                    })
                  },
                },
                {
                  onError: () => {
                    addToast(
                      <ToasterItem type="error">
                        <span>{t('errors.uploadFailed')}</span>
                      </ToasterItem>
                    )
                    setUploadingState((prev) => {
                      return {
                        ...prev,
                        filesMeta: {
                          ...prev.filesMeta,
                          [pathNicefy(file.path!)]: {
                            file,
                            progress:
                              prev.filesMeta[pathNicefy(file.path!)]?.progress ??
                              0,
                            status: 'error',
                          },
                        },
                      }
                    })
                  },
                  onSettled: () => {
                    resolve()
                  },
                }
              )
            })
        )
      }
      for (const promise of promises) {
        await promise()
      }
      setUploadingState((prev) => ({
        ...prev,
        step: UploadingStep.DONE,
      }))
    },
  })

  useEffect(() => {
    if (fileUploadsToastId.current) {
      // If the uploading state is "upload_files" and there are no files, we dismiss the toast.
      // It can happen if the upload fails for unknown reasons.
      if (
        (uploadingState.step === UploadingStep.UPLOAD_FILES &&
          Object.keys(uploadingState.filesMeta).length === 0) ||
        uploadingState.step === UploadingStep.NONE
      ) {
        toast.dismiss(fileUploadsToastId.current)
        fileUploadsToastId.current = null
      } else {
        toast.update(fileUploadsToastId.current, {
          render: <FileUploadToast uploadingState={uploadingState} />,
        })
      }
    }
  }, [uploadingState])

  useEffect(() => {
    const unloadCallback = (event: BeforeUnloadEvent) => {
      if (uploadingState.step === UploadingStep.UPLOAD_FILES) {
        event.preventDefault()
      }
      return ''
    }

    window.addEventListener('beforeunload', unloadCallback)
    return () => window.removeEventListener('beforeunload', unloadCallback)
  }, [uploadingState.step])

  return {
    dropZone,
  }
}
