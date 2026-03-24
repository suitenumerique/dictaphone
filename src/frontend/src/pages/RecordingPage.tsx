import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import { useGetFile } from '@/features/files/api/getFile.ts'
import { AudioPlayer } from '@/features/ui/preview/audio-player/AudioPlayer.tsx'

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
      <AudioPlayer src={recording.url!} />

      <div>Recording page {JSON.stringify(recording)}</div>
    </ConnectedLayout>
  )
}
