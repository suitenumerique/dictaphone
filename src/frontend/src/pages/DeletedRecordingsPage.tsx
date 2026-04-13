import { useListMyFilesInfinite } from '@/features/files/api/listFiles.ts'
import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import { ListRecordings } from '@/features/recordings/components/ListRecordings.tsx'

const PAGE_SIZE = 10

export function DeletedRecordingsPage() {
  const filesQ = useListMyFilesInfinite({
    filters: {
      type: 'audio_recording',
      upload_state: 'ready',
      is_creator_me: true,
      is_deleted: true,
    },
    pageSize: PAGE_SIZE,
  })

  return (
    <ConnectedLayout>
      <div className="recordings-page">
        <ListRecordings
          queryData={filesQ}
          isDropZoneActive={false}
          isTrashPage={true}
        />
      </div>
    </ConnectedLayout>
  )
}
