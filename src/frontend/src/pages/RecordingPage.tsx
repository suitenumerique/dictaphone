import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import { useGetFile } from '@/features/files/api/getFile.ts'
import {
  AudioPlayer,
  AudioPlayerHandle,
} from '@/features/ui/preview/audio-player/AudioPlayer.tsx'
import { useCallback, useMemo, useRef, useState } from 'react'
import { Transcript } from '@/features/recordings/components/Transcript.tsx'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs.ts'
import { Badge } from '@gouvfr-lasuite/ui-kit'
import { useTranslation } from 'react-i18next'
import { FileActionMenu } from '@/features/recordings/components/FileActionMenu.tsx'

export function RecordingPage({ recordingId }: { recordingId: string }) {
  const { t } = useTranslation('recordings')
  const playerRef = useRef<AudioPlayerHandle>(null)
  const [currentTime, setCurrentTime] = useState(0)

  const recordingQ = useGetFile(recordingId)
  const { lastAiJobTranscript } = useMemo(
    () => getMainAiJobs(recordingQ.data?.ai_jobs),
    [recordingQ.data?.ai_jobs]
  )

  const seekTo = useCallback((seconds: number) => {
    playerRef.current?.seekTo(seconds)
    setCurrentTime(seconds)
  }, [])

  if (recordingQ.isPending) {
    return (
      <ConnectedLayout>
        <div />
      </ConnectedLayout>
    )
  }

  if (!recordingQ.data || recordingQ.data.deleted_at !== null) {
    return (
      <ConnectedLayout>
        <div className="recording-page__not-found">
          <span className="material-icons">search_off</span>
          {t('notFound')}
        </div>
      </ConnectedLayout>
    )
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
              extraTitle={
                <>
                  {recording.deleted_at && (
                    <Badge type="warning">{t('deleted')}</Badge>
                  )}
                  <FileActionMenu file={recording} largeTrigger />
                </>
              }
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
        </div>
      </div>
    </ConnectedLayout>
  )
}
