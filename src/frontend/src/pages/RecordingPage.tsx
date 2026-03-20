import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import { useGetFile } from '@/features/files/api/getFile.ts'
import Player from '@/features/recordings/components/Player.tsx'

export function RecordingPage({ recordingId }: { recordingId: string }) {
  const recordingQ = useGetFile(recordingId)

  if (recordingQ.isPending) {
    return <span>Loading...</span>
  }
  if (!recordingQ.data) {
    return <span>No recording</span>
  }
  const recording = recordingQ.data
  return (
    <ConnectedLayout>
      <Player src={recording.url!} />

      <div>Recording page {JSON.stringify(recording)}</div>
    </ConnectedLayout>
  )
}
