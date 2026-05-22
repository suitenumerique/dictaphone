import { useListMyFilesInfinite } from '@/features/files/api/listFiles.ts'
import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import { ListRecordings } from '@/features/recordings/components/ListRecordings.tsx'
import { useUploadZone } from '@/hooks/useUpload.tsx'
import clsx from 'clsx'
import LogoApp from '@/layout/LogoApp.tsx'
import { useTranslation } from 'react-i18next'
import { FileShare } from '@gouvfr-lasuite/ui-kit'
import { useLocation } from 'wouter'
import { Button, Tooltip } from '@gouvfr-lasuite/cunningham-react'
import { RecoverList } from '../features/recordings/components/RecoverList'
import { useConfig } from '@/api/useConfig.ts'
import { formatFileSize } from '@/features/recordings/utils/formatFileSize.ts'
import { useMemo } from 'react'

const PAGE_SIZE = 10

export default function RecordingsPage() {
  const { t } = useTranslation(['recordings', 'record'])
  const [, navigate] = useLocation()
  const { data: appConfig } = useConfig()

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
  const supportedFormats = useMemo(
    () => appConfig?.audio_recording.allowed_extensions ?? [],
    [appConfig]
  )
  const maxFileSize = useMemo(
    () => appConfig?.audio_recording.max_size ?? 0,
    [appConfig]
  )

  const uploadTooltipContent = useMemo(
    () => (
      <div>
        <div>{t('uploadTooltip.title')}</div>
        <div>
          {t('uploadTooltip.supportedFormats', {
            formats:
              supportedFormats.length > 0
                ? supportedFormats.map((el) => el.replace('.', ''))
                : [t('uploadTooltip.noSupportedFormats')],
            formatParams: {
              formats: {
                type: 'conjunction',
                style: 'long',
              },
            },
          })}
        </div>
        <div>
          {t('uploadTooltip.maxFileSize', {
            maxSize: formatFileSize(maxFileSize),
          })}
        </div>
      </div>
    ),
    [supportedFormats, maxFileSize, t]
  )

  const handleStartNewRecording = () => {
    navigate('/new-recording')
  }

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
                onClick={handleStartNewRecording}
                className="recordings-actions__record-button"
                color="error"
                variant="secondary"
              >
                <span className="material-icons">radio_button_checked</span>
                {t('record:newRecording')}
              </Button>

              <Tooltip
                content={uploadTooltipContent}
                placement="top"
              >
                <Button
                  aria-label={t('cta')}
                  onClick={() =>
                    document.getElementById('import-files')?.click()
                  }
                  variant="bordered"
                  color="neutral"
                  icon={<FileShare />}
                ></Button>
              </Tooltip>
            </div>
            <div className="recordings-actions__warning">
              {t('record:consentWarning')}
            </div>
          </div>
        </div>

        <RecoverList />
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
