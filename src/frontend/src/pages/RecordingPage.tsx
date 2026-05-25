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
  ArrowUpRight,
  Badge,
  Calendar2,
  Clock,
  Copy,
  Shared,
  useResponsive,
} from '@gouvfr-lasuite/ui-kit'
import { useTranslation } from 'react-i18next'
import { FileActionMenu } from '@/features/recordings/components/FileActionMenu.tsx'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { ApiAiJob } from '@/features/ai-jobs/api/types.ts'
import { useOpenInDocsMutation } from '@/features/ai-jobs/api/fetch.ts'
import { useLocation } from 'wouter'
import { intervalToDuration } from 'date-fns'
import {
  buildTranscriptMarkdown,
  TranscriptViewSegment,
} from '@/features/ai-jobs/utils/transcript.ts'
import {
  addToast,
  ToasterItem,
} from '@/features/ui/components/toaster/Toaster.tsx'

function OpenInDocsButton({
  lastAiJobTranscript,
}: {
  lastAiJobTranscript: ApiAiJob | null
}) {
  const { t } = useTranslation('recordings')
  const openInDocs = useOpenInDocsMutation()
  const handleOpenInDocs = useCallback(() => {
    if (
      lastAiJobTranscript?.id &&
      lastAiJobTranscript.status === 'success' &&
      lastAiJobTranscript.docs_app_id
    ) {
      openInDocs.mutate(lastAiJobTranscript, {
        onSuccess: (res) => {
          window.open(res.doc_url, '_blank')
        },
      })
    }
  }, [lastAiJobTranscript, openInDocs])
  const { isMobile } = useResponsive()

  return (
    <Button
      onClick={handleOpenInDocs}
      size="small"
      variant="secondary"
      disabled={
        openInDocs.isPending ||
        lastAiJobTranscript?.status !== 'success' ||
        !lastAiJobTranscript?.docs_app_id
      }
      aria-label={t('transcript.openInDocsCta')}
      icon={<ArrowUpRight />}
      children={!isMobile ? t('transcript.openInDocsCta') : undefined}
    />
  )
}

export default function RecordingPage({
  recordingId,
}: {
  recordingId: string
}) {
  const { t } = useTranslation(['recordings', 'shared'])
  const [, navigate] = useLocation()
  const playerRef = useRef<AudioPlayerHandle>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [transcriptSegments, setTranscriptSegments] = useState<
    TranscriptViewSegment[]
  >([])

  const numberOfParticipants = useMemo(() => {
    if (transcriptSegments.length === 0) {
      return null
    } else {
      const speakers = new Set<string>(
        transcriptSegments.map((el) => el.speaker).filter(Boolean) as string[]
      )
      return speakers.size
    }
  }, [transcriptSegments])

  const recordingQ = useGetFile(recordingId)
  const recording = recordingQ.data

  const { lastAiJobTranscript } = useMemo(
    () => getMainAiJobs(recordingQ.data?.ai_jobs),
    [recordingQ.data?.ai_jobs]
  )

  const seekTo = useCallback((seconds: number) => {
    playerRef.current?.seekTo(seconds)
    setCurrentTime(seconds)
  }, [])
  const { isMobile } = useResponsive()

  const transcriptMarkdown = useMemo(() => {
    if (!recording) return null
    return buildTranscriptMarkdown({
      title: recording.title,
      transcriptSegments,
      speakerLabel: t('transcript.speaker'),
    })
  }, [recording, transcriptSegments, t])
  const handleCopy = useCallback(() => {
    navigator.clipboard
      .writeText(transcriptMarkdown!)
      .then(() => {
        addToast(
          <ToasterItem type="info">{t('transcript.copySuccess')}</ToasterItem>
        )
      })
      .catch(() => {
        addToast(
          <ToasterItem type="error">{t('transcript.copyError')}</ToasterItem>
        )
      })
  }, [t, transcriptMarkdown])

  if (recordingQ.isPending) {
    return (
      <ConnectedLayout>
        <div />
      </ConnectedLayout>
    )
  }

  if (!recording || recording.deleted_at !== null) {
    return (
      <ConnectedLayout>
        <div className="recording-page__not-found">
          <span className="material-icons" aria-hidden="true">
            search_off
          </span>
          {t('notFound')}
        </div>
      </ConnectedLayout>
    )
  }

  return (
    <ConnectedLayout>
      <div className="recording-page">
        <div className="recording-page__actions-buttons">
          <Button
            aria-label={t('shared:actions.back')}
            variant="bordered"
            icon={<ArrowLeft />}
            size="small"
            onClick={() => navigate('/recordings')}
          >
            {t('shared:actions.back')}
          </Button>

          <div className="recording-page__actions-buttons__right">
            {!isMobile && (
              <>
                <Button
                  aria-label={t('shared:actions.copyText')}
                  size="small"
                  variant="tertiary"
                  color="neutral"
                  icon={<Copy />}
                  disabled={
                    lastAiJobTranscript?.status !== 'success' ||
                    !transcriptMarkdown
                  }
                  children={t('shared:actions.copyText')}
                  onClick={handleCopy}
                />
                <OpenInDocsButton lastAiJobTranscript={lastAiJobTranscript} />
              </>
            )}

            <FileActionMenu
              file={recording}
              largeTrigger={isMobile}
              showCopyText={isMobile}
              showOpenInDocs={isMobile}
            />
          </div>
        </div>
        <h1 className="recording-page__title">{recording.title}</h1>
        <table
          className="recording-page__metadata"
          aria-label={t('metadata.ariaLabel')}
        >
          <tbody>
            <tr>
              <td>
                <div className="recording-page__metadata__item">
                  <Calendar2
                    className="recording-page__metadata__item__icon"
                    aria-hidden="true"
                  />
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
                  <Clock
                    className="recording-page__metadata__item__icon"
                    aria-hidden="true"
                  />
                  <span>
                    {t('shared:utils.duration', {
                      duration: intervalToDuration({
                        start: 0,
                        end:
                          Math.max(recording.duration_seconds || 1, 1) * 1000,
                      }),
                    })}
                  </span>
                </div>
              </td>
              {numberOfParticipants !== null && (
                <td>
                  <div className="recording-page__metadata__item">
                    <Shared
                      className="recording-page__metadata__item__icon"
                      aria-hidden="true"
                    />
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
          durationSecondsEstimate={recording.duration_seconds}
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
          setTranscriptSegments={setTranscriptSegments}
        />
      </div>
    </ConnectedLayout>
  )
}
