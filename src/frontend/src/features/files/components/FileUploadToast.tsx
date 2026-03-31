import { ToasterItem } from '@/features/ui/components/toaster/Toaster'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import { CircularProgress } from '@/features/ui/components/circular-progress/CircularProgress'
import prettyBytes from 'pretty-bytes'
import { ToastContentProps } from 'react-toastify'
import { Spinner } from '@gouvfr-lasuite/ui-kit'
import { UploadingState } from '@/hooks/useUpload.tsx'

export const FileUploadToast = (
  props: {
    uploadingState: UploadingState
  } & Partial<ToastContentProps>
) => {
  const { t } = useTranslation('upload')
  const [isOpen, setIsOpen] = useState(true)
  const pendingFilesCount = Object.values(
    props.uploadingState.filesMeta
  ).filter(
    (meta) => meta.status === 'uploading'
  ).length
  const doneFilesCount = Object.values(props.uploadingState.filesMeta).filter(
    (meta) => meta.status === 'done'
  ).length
  const failedFilesCount = Object.values(props.uploadingState.filesMeta).filter(
    (meta) => meta.status === 'error'
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
                    <span>{name}</span>
                    <span className="file-upload-toast__files__item__size">
                      {prettyBytes(meta.file.size)}
                    </span>
                  </div>
                  <div className="file-upload-toast__files__item__progress">
                    <CircularProgress progress={meta.progress} />
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
                {pendingFilesCount > 0
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
