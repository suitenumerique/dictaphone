import { FileTrigger, Pressable } from 'react-aria-components'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import {
  ListFilesParams,
  useListMyFiles,
} from '@/features/files/api/listFiles.ts'
import { useCreateFile } from '@/features/files/api/createFile.ts'
import { useConfig } from '@/api/useConfig.ts'
import ConnectedLayout from '@/layout/ConnectedLayout.tsx'

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
  const { data: appConfig } = useConfig()
  const filesQ = useListMyFiles(listFilesQueryParams)
  const createFileMutation = useCreateFile()

  const handleNewFilePicked = (file: File) => {
    createFileMutation.mutate({
      file,
      onProgress: (progress) => {
        console.log(`Upload progress: ${progress}%`)
      },
    })
  }

  return (
    <ConnectedLayout>
      <FileTrigger
        acceptedFileTypes={appConfig?.audio_recording?.allowed_mimetypes ?? []}
        onSelect={(e) => {
          if (e && e.item(0)) {
            const file = e.item(0) as File
            handleNewFilePicked(file)
          }
        }}
      >
        <Pressable>
          <Button
            aria-label={'Load audio recording from your device'}
            disabled={createFileMutation.isPending}
            data-attr="input-file-select-audio-recording"
          >
            Add recording
          </Button>
        </Pressable>
      </FileTrigger>

      {filesQ.isPending && <span>Loading...</span>}
      {filesQ.data && filesQ.data.count === 0 && <span>No files</span>}
      {filesQ.data && filesQ.data.results.length > 0 && (
        <div>
          {filesQ.data.results.map((file) => (
            <div key={file.id}>
              <span>{file.title}</span>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <audio controls src={file.url!} />
            </div>
          ))}
        </div>
      )}
    </ConnectedLayout>
  )
}
