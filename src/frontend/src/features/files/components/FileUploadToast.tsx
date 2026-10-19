import { addToast, ToasterItem } from '@/features/ui/components/toaster/Toaster'
import { Button } from '@gouvfr-lasuite/ui-components'
import { useEffect, useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import { CircularProgress } from '@/features/ui/components/circular-progress/CircularProgress'
import prettyBytes from 'pretty-bytes'
import { toast, type Id, ToastContentProps } from 'react-toastify'
import { Spinner } from '@gouvfr-lasuite/ui-components'
import { useUploadsPaused } from '@/api/rateLimits'
import {
  useImportUploads,
  type FileUploadMeta,
  type UploadingState,
} from '@/features/files/importUploads'

const isPending = (meta: FileUploadMeta) =>
  meta.status === 'queued' || meta.status === 'uploading'

export const FileUploadToast = (
  props: {
    uploadingState: UploadingState
  } & Partial<ToastContentProps>
) => {
  const { t } = useTranslation('upload')
  const [isOpen, setIsOpen] = useState(true)
  const uploadsPaused = useUploadsPaused()
  const pendingFilesCount = Object.values(
    props.uploadingState.filesMeta
  ).filter(isPending).length
  const doneFilesCount = Object.values(props.uploadingState.filesMeta).filter(
    (meta) => meta.status === 'done'
  ).length
  const failedFilesCount = Object.values(props.uploadingState.filesMeta).filter(
    (meta) => meta.status === 'error'
  ).length
  const pausedCount = Object.values(props.uploadingState.filesMeta).filter(
    (meta) => uploadsPaused && meta.status === 'queued'
  ).length
  // Does not show the files list and the open button.
  const simpleMode = props.uploadingState.step === 'preparing'

  useEffect(() => {
    if (props.uploadingState.step === 'upload_files') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsOpen(true)
    }
  }, [props.uploadingState.step])

  useEffect(() => {
    if (pendingFilesCount === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsOpen(false)
    }
  }, [pendingFilesCount])

  return (
    <ToasterItem className="file-upload-toast__item">
      <div className="file-upload-toast">
        <div
          className={clsx('file-upload-toast__files', {
            'file-upload-toast__files--closed': !isOpen,
          })}
        >
          {Object.entries(props.uploadingState.filesMeta).map(
            ([name, meta]) => {
              return (
                <div key={name} className="file-upload-toast__files__item">
                  <div className="file-upload-toast__files__item__name">
                    <span>{meta.file.name}</span>
                    {uploadsPaused && meta.status === 'queued' && (
                      <span>{t('rateLimit.paused')}</span>
                    )}
                    <span className="file-upload-toast__files__item__size">
                      {prettyBytes(meta.file.size)}
                    </span>
                  </div>
                  <div className="file-upload-toast__files__item__progress">
                    <CircularProgress
                      progress={meta.progress}
                      status={meta.status === 'queued' ? 'error' : meta.status}
                    />
                  </div>
                </div>
              )
            }
          )}
        </div>
        <div className="file-upload-toast__description">
          <div className="file-upload-toast__description__text">
            {simpleMode ? (
              <>
                <Spinner />
                {t(`uploader.steps.${props.uploadingState.step}`)}
              </>
            ) : (
              <>
                {pausedCount > 0
                  ? t('rateLimit.title')
                  : pendingFilesCount > 0
                    ? t('uploader.files.description', {
                        count: pendingFilesCount,
                      })
                    : doneFilesCount > 0
                      ? t('uploader.files.description_done', {
                          count: doneFilesCount,
                        })
                      : failedFilesCount > 0
                        ? t('errors.uploadFailed')
                        : null}
              </>
            )}
          </div>
          <div>
            {!simpleMode && (
              <Button
                variant="tertiary"
                size="small"
                icon={
                  <span className="material-icons">
                    {isOpen ? 'keyboard_arrow_up' : 'keyboard_arrow_down'}
                  </span>
                }
                onClick={() => setIsOpen(!isOpen)}
              ></Button>
            )}

            <Button
              onClick={props.closeToast}
              disabled={pendingFilesCount > 0}
              variant="tertiary"
              size="small"
              icon={<span className="material-icons">close</span>}
            ></Button>
          </div>
        </div>
      </div>
    </ToasterItem>
  )
}

/** Feedback stays mounted while imports continue across navigation. */
export function ImportUploadFeedback() {
  const uploadingState = useImportUploads()
  const fileUploadsToastId = useRef<Id | null>(null)

  useEffect(() => {
    if (
      !fileUploadsToastId.current &&
      (uploadingState.step === 'preparing' ||
        Object.values(uploadingState.filesMeta).some(isPending))
    ) {
      fileUploadsToastId.current = addToast(
        <FileUploadToast uploadingState={uploadingState} />,
        {
          autoClose: false,
          toastId: 'import-uploads',
          onClose: () => {
            fileUploadsToastId.current = null
          },
        }
      )
    }
    if (fileUploadsToastId.current) {
      // If the uploading state is "upload_files" and there are no files, we dismiss the toast.
      // It can happen if the upload fails for unknown reasons.
      if (
        (uploadingState.step !== 'preparing' &&
          Object.keys(uploadingState.filesMeta).length === 0) ||
        uploadingState.step === 'none'
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
      if (Object.values(uploadingState.filesMeta).some(isPending)) {
        event.preventDefault()
      }
      return ''
    }

    window.addEventListener('beforeunload', unloadCallback)
    return () => window.removeEventListener('beforeunload', unloadCallback)
  }, [uploadingState])

  return null
}
