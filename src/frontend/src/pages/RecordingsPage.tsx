import { useListMyFilesInfinite } from '@/features/files/api/listFiles.ts'
import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import { ListRecordings } from '@/features/recordings/components/ListRecordings.tsx'
import { useUploadZone } from '@/hooks/useUpload.tsx'
import clsx from 'clsx'
import LogoApp from '@/layout/LogoApp.tsx'
import { useTranslation } from 'react-i18next'

const PAGE_SIZE = 10

export function RecordingsPage() {
  const { t } = useTranslation('recordings')
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
        <ListRecordings
          queryData={filesQ}
          isDropZoneActive={isDropZoneActive}
        />
      </div>
      <input
        {...dropZone.getInputProps({
          id: 'import-files',
        })}
      />
    </ConnectedLayout>
  )
}
