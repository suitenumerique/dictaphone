import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import { useGetFile } from '@/features/files/api/getFile.ts'
import {
  AudioPlayer,
  AudioPlayerHandle,
} from '@/features/ui/preview/audio-player/AudioPlayer.tsx'
import { useCallback, useMemo, useRef, useState } from 'react'
import { Transcript } from '@/features/recordings/components/Transcript.tsx'
import { Summary } from '@/features/recordings/components/Summary.tsx'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs.ts'

export function RecordingPage({ recordingId }: { recordingId: string }) {
  const playerRef = useRef<AudioPlayerHandle>(null)
  const [currentTime, setCurrentTime] = useState(0)

  const recordingQ = useGetFile(recordingId)
  const { lastAiJobTranscript, lastAiJobSummary } = useMemo(
    () => getMainAiJobs(recordingQ.data?.ai_jobs),
    [recordingQ.data?.ai_jobs]
  )

  const seekTo = useCallback((seconds: number) => {
    playerRef.current?.seekTo(seconds)
    setCurrentTime(seconds)
  }, [])

  if (recordingQ.isPending) {
    return <span>Loading...</span>
  }
  if (!recordingQ.data) {
    return <span>No recording</span>
  }
  const recording = recordingQ.data
  return (
    <ConnectedLayout>
      <div className="recording-page">
        <div className="recording-page__player">
          <div className="recording-page__card ">
            <AudioPlayer
              src={recording.url!}
              ref={playerRef}
              title={recording.title}
              onTimeUpdate={setCurrentTime}
            />
          </div>
        </div>

        <div className="recording-page__content">
          <div className="recording-page__card">
            <Transcript
              lastAiJobTranscript={lastAiJobTranscript}
              seekTo={seekTo}
              currentTime={currentTime}
            />
          </div>
          <div className="recording-page__card">
            <Summary lastAiJobSummary={lastAiJobSummary} />
          </div>
        </div>
      </div>
    </ConnectedLayout>
  )
}
