import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import { useGetFile } from '@/features/files/api/getFile.ts'
import {
  AudioPlayer,
  AudioPlayerHandle,
} from '@/features/ui/preview/audio-player/AudioPlayer.tsx'
import { useCallback, useMemo, useRef, useState } from 'react'
import { Transcript } from '@/features/recordings/components/Transcript.tsx'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs.ts'
import {
  ArrowLeft,
  Badge,
  Calendar2,
  Clock,
  Copy,
  Shared,
} from '@gouvfr-lasuite/ui-kit'
import { useTranslation } from 'react-i18next'
import { FileActionMenu } from '@/features/recordings/components/FileActionMenu.tsx'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { ApiAiJob } from '@/features/ai-jobs/api/types.ts'
import { useOpenInDocsMutation } from '@/features/ai-jobs/api/fetch.ts'
import { useLocation } from 'wouter'
import { intervalToDuration } from 'date-fns'

function OpenInDocsButton({
  lastAiJobTranscript,
}: {
  lastAiJobTranscript: ApiAiJob | null
}) {
  const { t } = useTranslation('recordings')
  const openInDocs = useOpenInDocsMutation()
  const handleOpenInDocs = useCallback(() => {
    if (lastAiJobTranscript?.id && lastAiJobTranscript.status === 'success') {
      openInDocs.mutate(lastAiJobTranscript, {
        onSuccess: (res) => {
          window.open(res.doc_url, '_blank')
        },
      })
    }
  }, [lastAiJobTranscript, openInDocs])

  return (
    <Button
      onClick={handleOpenInDocs}
      size="small"
      variant="primary"
      disabled={lastAiJobTranscript?.status !== 'success'}
      icon={
        <img
          src="/assets/files/icons/docs-mono.svg"
          alt="Docs"
          width={20}
          height={20}
        />
      }
    >
      {t('transcript.openInDocsCta')}
    </Button>
  )
}

export function RecordingPage({ recordingId }: { recordingId: string }) {
  const { t } = useTranslation('recordings')
  const [, navigate] = useLocation()
  const playerRef = useRef<AudioPlayerHandle>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [numberOfParticipants, setNumberOfParticipants] = useState<
    null | number
  >(null)

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
        <div className="recording-page__actions-buttons">
          <Button
            variant="bordered"
            icon={<ArrowLeft />}
            size="small"
            onClick={() => navigate('/recordings')}
          >
            {t('shared:actions.back')}
          </Button>
          <div className="recording-page__actions-buttons__right">
            <Button
              size="small"
              variant="tertiary"
              color="neutral"
              icon={<Copy />}
              disabled={lastAiJobTranscript?.status !== 'success'}
            >
              {t('shared:actions.copy')}
            </Button>
            <OpenInDocsButton lastAiJobTranscript={lastAiJobTranscript} />
            <FileActionMenu file={recording} />
          </div>
        </div>
        <h1 className="recording-page__title">{recording.title}</h1>
        <table className="recording-page__metadata">
          <tbody>
            <tr>
              <td>
                <div className="recording-page__metadata__item">
                  <Calendar2 className="recording-page__metadata__item__icon" />
                  <span>
                    {t('shared:utils.formatDate', {
                      // value: recording.created_at,
                      value: '2024-04-12',
                    })}
                  </span>
                </div>
              </td>
              <td>
                <div className="recording-page__metadata__item">
                  <Clock className="recording-page__metadata__item__icon" />
                  <span>
                    {t('shared:utils.duration', {
                      duration: intervalToDuration({
                        start: 0,
                        end: recording.duration_seconds * 1000,
                      }),
                    })}
                  </span>
                </div>
              </td>
              {numberOfParticipants !== null && (
                <td>
                  <div className="recording-page__metadata__item">
                    <Shared className="recording-page__metadata__item__icon" />
                    <span>{numberOfParticipants}</span>
                  </div>
                </td>
              )}
            </tr>
          </tbody>
        </table>
        <AudioPlayer
          src={recording.url!}
          ref={playerRef}
          title={recording.title}
          onTimeUpdate={setCurrentTime}
          extraTitle={
            recording.deleted_at ? (
              <Badge type="warning">{t('deleted')}</Badge>
            ) : undefined
          }
        />
        <Transcript
          lastAiJobTranscript={lastAiJobTranscript}
          seekTo={seekTo}
          currentTime={currentTime}
          setNumberParticipant={setNumberOfParticipants}
        />
      </div>
    </ConnectedLayout>
  )
}
