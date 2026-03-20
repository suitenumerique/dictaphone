import {
  ListFilesParams,
  useListMyFiles,
} from '@/features/files/api/listFiles.ts'
import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import ListRecordings from '@/features/recordings/components/ListRecordings.tsx'
import RecordingUploadComponent from '@/features/recordings/components/RecordingUploadComponent.tsx'

const listFilesQueryParams: ListFilesParams = {
  filters: {
    type: 'audio_recording',
    upload_state: 'ready',
    is_creator_me: true,
    is_deleted: false,
  },
  pagination: {
    page: 1,
    pageSize: 20,
  },
}

export function RecordingsPage() {
  const filesQ = useListMyFiles(listFilesQueryParams)

  return (
    <ConnectedLayout>
      <RecordingUploadComponent />
      <ListRecordings queryData={filesQ} />
    </ConnectedLayout>
  )
}
