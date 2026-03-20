import {
  Button,
  Modal,
  ModalSize,
  Tooltip,
} from '@gouvfr-lasuite/cunningham-react'
import { useMemo, useState } from 'react'
import { FileRejection, useDropzone } from 'react-dropzone'
import { useConfig } from '@/api/useConfig.ts'
import { useCreateFile } from '@/features/files/api/createFile.ts'
import { getAudioDuration } from '@/features/recordings/utils/getAudioDuration.ts'
import { useTranslation } from 'react-i18next'
import { intervalToDuration } from 'date-fns'
import { ProgressBar } from '@/components/ProgressBar.tsx'
import { v4 as uuidV4 } from 'uuid'
import { useDisablePageRefresh } from '@/hooks/disablePageRegresh.ts'

// 3 hours
const MAX_DURATION_SECONDS = 60 * 60 * 3

type UploadStatus = 'ready' | 'invalid' | 'uploading' | 'uploaded' | 'error'

type SelectedFile = {
  id: string
  file: File
} & (
  | {
      isValid: true
      durationSeconds: number
      uploadStatus: UploadStatus
      progress: number
    }
  | { isValid: false; errors: string[] }
)

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) {
    return `${bytes} B`
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function RecordingUploadComponent() {
  const { data: appConfig } = useConfig()
  const { t } = useTranslation(['upload', 'shared'])
  const createFileMutation = useCreateFile()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  useDisablePageRefresh(isUploading)
  const [files, setFiles] = useState<SelectedFile[]>([])

  const allowedMimetypes = useMemo(
    () => appConfig?.audio_recording.allowed_mimetypes ?? [],
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

  const onDrop = async (
    acceptedFiles: File[],
    fileRejections: FileRejection[]
  ) => {
    const out: SelectedFile[] = []
    for (const rejection of fileRejections) {
      out.push({
        id: uuidV4(),
        file: rejection.file,
        isValid: false,
        errors: rejection.errors.map((error) => {
          if (error.code === 'file-invalid-type') {
            return t('errors.unsupportedMimeType', {
              mimeType: rejection.file.type,
            })
          } else if (error.code === 'file-too-large') {
            return t('errors.tooLarge', {
              maxSize: formatFileSize(maxSize),
            })
          } else {
            return `Error: ${error.code}`
          }
        }),
      })
    }

    for (const file of acceptedFiles) {
      const durationSeconds = await getAudioDuration(file)
      if (durationSeconds === null) {
        out.push({
          id: uuidV4(),
          file,
          isValid: false,
          errors: [t('errors.invalidAudio')],
        })
      } else if (durationSeconds > MAX_DURATION_SECONDS) {
        out.push({
          id: uuidV4(),
          file,
          isValid: false,
          errors: [
            t('errors.tooLong', {
              maxDuration: intervalToDuration({
                start: 0,
                end: MAX_DURATION_SECONDS * 1000,
              }),
              duration: intervalToDuration({
                start: 0,
                end: durationSeconds * 1000,
              }),
            }),
          ],
        })
      } else {
        out.push({
          id: uuidV4(),
          isValid: true,
          durationSeconds,
          uploadStatus: 'ready',
          progress: 0,
          file,
        })
      }
    }

    setFiles((previous) =>
      [...previous, ...out].sort((a, b) => a.id.localeCompare(b.id))
    )
  }

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    maxSize,
    disabled: isUploading,
  })

  const validFiles = files.filter(
    (entry) => entry.isValid && entry.uploadStatus === 'ready'
  )

  const handleUploadValidFiles = async () => {
    if (validFiles.length === 0 || isUploading) {
      return
    }

    setIsUploading(true)
    let hasErrors = false

    for (const validEntry of validFiles) {
      setFiles((previous) =>
        previous.map((fileEntry) =>
          fileEntry.id === validEntry.id
            ? { ...fileEntry, uploadStatus: 'uploading', progress: 0 }
            : fileEntry
        )
      )

      try {
        await createFileMutation.mutateAsync({
          file: validEntry.file,
          onProgress: (progress) => {
            setFiles((previous) =>
              previous.map((fileEntry) =>
                fileEntry.id === validEntry.id
                  ? { ...fileEntry, progress }
                  : fileEntry
              )
            )
          },
        })

        setFiles((previous) =>
          previous.map((fileEntry) =>
            fileEntry.id === validEntry.id
              ? { ...fileEntry, uploadStatus: 'uploaded', progress: 100 }
              : fileEntry
          )
        )
      } catch {
        setFiles((previous) =>
          previous.map((fileEntry) =>
            fileEntry.id === validEntry.id
              ? {
                  ...fileEntry,
                  uploadStatus: 'error',
                }
              : fileEntry
          )
        )
        hasErrors = true
      }
    }

    setIsUploading(false)

    if (!hasErrors) {
      setIsModalOpen(false)
      setFiles([])
    }
  }

  const closeModal = () => {
    if (isUploading) {
      return
    }
    setFiles([])
    setIsModalOpen(false)
  }

  const handleRemoveFile = (fileId: string) => {
    if (isUploading) {
      return
    }

    setFiles((previous) =>
      previous.filter((fileEntry) => fileEntry.id !== fileId)
    )
  }

  return (
    <>
      <Button
        aria-label={'Upload a recording file'}
        onClick={() => setIsModalOpen(true)}
        data-attr="input-file-select-audio-recording"
        icon={<span className="material-icons">upload</span>}
        variant="secondary"
      >
        {t('cta')}
      </Button>

      <Modal
        size={ModalSize.MEDIUM}
        isOpen={isModalOpen}
        onClose={closeModal}
        preventClose={isUploading}
        closeOnEsc={!isUploading}
        closeOnClickOutside={!isUploading}
        title={t('title')}
        rightActions={
          <>
            <Button
              variant="secondary"
              onClick={closeModal}
              disabled={isUploading}
            >
              {t('shared:actions.cancel')}
            </Button>
            <Button
              onClick={handleUploadValidFiles}
              disabled={
                validFiles.length === 0 ||
                validFiles.length !== files.length ||
                isUploading
              }
            >
              {t('uploadFilesCta')}
            </Button>
          </>
        }
      >
        <div className="recording-upload-modal">
          {!isUploading && (
            <div
              {...getRootProps({
                className: `recording-upload-dropzone ${isDragActive ? 'active' : ''}`,
              })}
            >
              <input {...getInputProps()} />
              <p>{t('dragAndDropLabel')}</p>
              <p className="recording-upload-dropzone__hint">
                {t('maxFileSize', { value: formatFileSize(maxSize) })}
              </p>
              <p className="recording-upload-dropzone__hint">
                {t('maxDuration', {
                  maxDuration: intervalToDuration({
                    start: 0,
                    end: MAX_DURATION_SECONDS * 1000,
                  }),
                })}
              </p>
            </div>
          )}

          {files.length > 0 && (
            <ul className="recording-upload-list">
              {files.map((entry) => (
                <li key={entry.id} className="recording-upload-item">
                  <div className="recording-upload-item__main">
                    <div className="recording-upload-item__header">
                      <div className="recording-upload-item__title">
                        <span className="material-icons">audio_file</span>
                        <span>{entry.file.name}</span>
                      </div>
                      <Tooltip
                        content={isUploading ? '' : t('removeFileTooltip')}
                        placement="top"
                      >
                        <Button
                          size="small"
                          variant="tertiary"
                          onClick={() => handleRemoveFile(entry.id)}
                          disabled={isUploading}
                          icon={<span className="material-icons">delete</span>}
                        />
                      </Tooltip>
                    </div>
                    {entry.isValid && (
                      <div className="recording-upload-item__metadata">
                        <span>{formatFileSize(entry.file.size)}</span>
                        <span>|</span>
                        <span>
                          {t('duration', {
                            duration: intervalToDuration({
                              start: 0,
                              end: entry.durationSeconds * 1000,
                            }),
                          })}
                        </span>
                      </div>
                    )}
                  </div>

                  {entry.isValid ? (
                    <>
                      {(entry.uploadStatus === 'uploading' ||
                        entry.uploadStatus === 'uploaded') && (
                        <ProgressBar
                          value={entry.progress}
                          minValue={0}
                          maxValue={100}
                        />
                      )}
                      {entry.uploadStatus === 'error' && (
                        <div className="recording-upload-errors">
                          {t('errors.uploadFailed')}
                        </div>
                      )}
                    </>
                  ) : (
                    <ul className="recording-upload-errors">
                      {entry.errors.map((error, index) => (
                        <li key={`${entry.id}-error-${index}`}>{error}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Modal>
    </>
  )
}
