import {
  ListFilesParams,
  useListMyFiles,
} from '@/features/files/api/listFiles.ts'
import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import ListRecordings from '@/features/recordings/components/ListRecordings.tsx'
import { useMemo, useState } from 'react'
import { useUploadZone } from '@/hooks/useUpload.tsx'
import clsx from 'clsx'

const PAGE_SIZE = 10

export function RecordingsPage() {
  const [page, setPage] = useState(1)
  const listFilesQueryParams: ListFilesParams = useMemo(
    () => ({
      filters: {
        type: 'audio_recording',
        upload_state: 'ready',
        is_creator_me: true,
        is_deleted: false,
      },
      pagination: {
        page,
        pageSize: PAGE_SIZE,
      },
    }),
    [page]
  )

  const filesQ = useListMyFiles(listFilesQueryParams)
  const { dropZone } = useUploadZone()

  return (
    <ConnectedLayout>
      <div
        {...dropZone.getRootProps({
          className: clsx({
            'drop-zone--drag-in-progress':
              dropZone.isFocused ||
              dropZone.isDragAccept ||
              dropZone.isDragReject,
          }),
        })}
      >
        <ListRecordings
          queryData={filesQ}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
        />
        <input
          {...dropZone.getInputProps({
            id: 'import-files',
          })}
        />
      </div>
    </ConnectedLayout>
  )
}
