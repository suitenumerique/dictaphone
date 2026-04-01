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
import { CustomTabs, useResponsive } from '@gouvfr-lasuite/ui-kit'
import { useTranslation } from 'react-i18next'
import { FileActionMenu } from '@/features/recordings/components/FileActionMenu.tsx'

export function RecordingPage({ recordingId }: { recordingId: string }) {
  const { t } = useTranslation('recordings')
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

  const { isDesktop } = useResponsive()

  if (recordingQ.isPending) {
    return (
      <ConnectedLayout>
        <div />
      </ConnectedLayout>
    )
  }

  if (!recordingQ.data) {
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
              extraTitle={<FileActionMenu file={recording} largeTrigger />}
            />
          </div>
        </div>

        {isDesktop ? (
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
        ) : (
          <div className="recording-page__card">
            <CustomTabs
              defaultSelectedTab="transcript"
              tabs={[
                {
                  content: (
                    <Transcript
                      lastAiJobTranscript={lastAiJobTranscript}
                      seekTo={seekTo}
                      currentTime={currentTime}
                    />
                  ),
                  icon: 'format_align_left',
                  id: 'transcript',
                  label: t('transcript.title'),
                },
                {
                  content: <Summary lastAiJobSummary={lastAiJobSummary} />,
                  icon: 'unfold_less',
                  id: 'summary',
                  label: t('summary.title'),
                },
              ]}
            />
          </div>
        )}
      </div>
    </ConnectedLayout>
  )
}
