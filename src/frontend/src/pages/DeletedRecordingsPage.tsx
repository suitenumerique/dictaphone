import {
  ListFilesParams,
  useListMyFiles,
} from '@/features/files/api/listFiles.ts'
import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import ListRecordings from '@/features/recordings/components/ListRecordings.tsx'
import { useMemo, useState } from 'react'

const PAGE_SIZE = 10

export function DeletedRecordingsPage() {
  const [page, setPage] = useState(1)
  const listFilesQueryParams: ListFilesParams = useMemo(
    () => ({
      filters: {
        type: 'audio_recording',
        upload_state: 'ready',
        is_creator_me: true,
        is_deleted: true,
      },
      pagination: {
        page,
        pageSize: PAGE_SIZE,
      },
    }),
    [page]
  )

  const filesQ = useListMyFiles(listFilesQueryParams)

  return (
    <ConnectedLayout>
      <div className="recordings-page">
        <ListRecordings
          queryData={filesQ}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
          isDropZoneActive={false}
          isTrashPage={true}
        />
      </div>
    </ConnectedLayout>
  )
}
