import { useListMyFilesInfinite } from '@/features/files/api/listFiles.ts'
import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import { ListRecordings } from '@/features/recordings/components/ListRecordings.tsx'
import { useUploadZone } from '@/hooks/useUpload.tsx'
import clsx from 'clsx'
import LogoApp from '@/layout/LogoApp.tsx'
import { useTranslation } from 'react-i18next'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { FileShare } from '@gouvfr-lasuite/ui-kit'
import { useLocation } from 'wouter'

const PAGE_SIZE = 10

export default function RecordingsPage() {
  const { t } = useTranslation(['recordings', 'record'])
  const [, navigate] = useLocation()

  const filesQ = useListMyFilesInfinite({
    filters: {
      type: 'audio_recording',
      upload_state: 'ready',
      is_creator_me: true,
      is_deleted: false,
    },
    pageSize: PAGE_SIZE,
  })

  const { dropZone } = useUploadZone()
  const isDropZoneActive =
    dropZone.isFocused || dropZone.isDragAccept || dropZone.isDragReject

  return (
    <ConnectedLayout
      {...dropZone.getRootProps({
        className: clsx({
          'drop-zone--drag-in-progress': isDropZoneActive,
        }),
      })}
    >
      <div className="recordings-page">
        <div className="recordings-page__header">
          <LogoApp height={60} />
          <span>{t('subtitle')}</span>
        </div>
        <div
          className={clsx({
            'drop-zone--drag-in-progress-main-area': isDropZoneActive,
          })}
        >
          <div className="recordings-actions">
            <div className="first-row">
              <Button
                onClick={() => navigate('/new-recording?auto-start=true')}
                className="recordings-actions__record-button"
                color="error"
                variant="secondary"
              >
                <span className="material-icons">radio_button_checked</span>
                {t('record:newRecording')}
              </Button>

              <Button
                aria-label={t('cta')}
                onClick={() => document.getElementById('import-files')?.click()}
                variant="bordered"
                color="neutral"
                icon={<FileShare />}
              ></Button>
            </div>
            <div className="recordings-actions__warning">
              {t('record:consentWarning')}
            </div>
          </div>
        </div>

        <ListRecordings queryData={filesQ} />
      </div>
      <input
        {...dropZone.getInputProps({
          id: 'import-files',
        })}
      />
    </ConnectedLayout>
  )
}
