import { useTranscript } from '@/features/ai-jobs/api/fetch.ts'
import { Fragment, useCallback, useEffect, useMemo, useRef } from 'react'
import {
  buildTranscriptViewSegments,
  findActiveSegmentIndex,
  TranscriptViewSegment,
} from '@/features/ai-jobs/utils/transcript.ts'
import { ApiAiJob } from '@/features/ai-jobs/api/types.ts'
import { TranscriptSegment } from '@/features/recordings/components/TranscriptSegment.tsx'
import { Trans, useTranslation } from 'react-i18next'
import { Badge } from '@gouvfr-lasuite/ui-kit'
import { Skeleton } from '@/components/Skeleton'
import { useFormattedProcessingDuration } from '@/features/ai-jobs/utils/useFormattedProcessingDuration'

export function Transcript({
  lastAiJobTranscript,
  currentTime,
  seekTo,
  setTranscriptSegments,
}: {
  lastAiJobTranscript: ApiAiJob | null
  currentTime: number
  seekTo: (time: number) => void
  setTranscriptSegments: (segments: TranscriptViewSegment[]) => void
}) {
  const { t } = useTranslation('recordings')
  const transcriptContainerRef = useRef<HTMLDivElement>(null)
  const segmentRefs = useRef<Map<string, HTMLSpanElement>>(new Map())

  const setSegmentRef = useCallback(
    (id: string, element: HTMLSpanElement | null) => {
      if (!element) {
        segmentRefs.current.delete(id)
        return
      }
      segmentRefs.current.set(id, element)
    },
    []
  )

  const transcriptQ = useTranscript(lastAiJobTranscript)

  const transcriptSegments = useMemo(
    () => buildTranscriptViewSegments(transcriptQ.data),
    [transcriptQ.data]
  )
  useEffect(() => {
    setTranscriptSegments(transcriptSegments)
  }, [transcriptSegments, setTranscriptSegments])

  const activeSegmentIndex = useMemo(
    () => findActiveSegmentIndex(transcriptSegments, currentTime),
    [transcriptSegments, currentTime]
  )
  const activeSegment =
    activeSegmentIndex >= 0 ? transcriptSegments[activeSegmentIndex] : null
  const activeWordIndex = useMemo(() => {
    if (!activeSegment?.words.length) return -1
    return findActiveSegmentIndex(activeSegment.words, currentTime)
  }, [activeSegment, currentTime])

  useEffect(() => {
    const container = transcriptContainerRef.current
    const activeSegmentId = activeSegment?.id
    if (!container || !activeSegmentId) return

    const activeElement = segmentRefs.current.get(activeSegmentId)
    if (!activeElement) return

    const containerRect = container.getBoundingClientRect()
    const activeRect = activeElement.getBoundingClientRect()
    const isOutsideViewport =
      activeRect.top < containerRect.top + 24 ||
      activeRect.bottom > containerRect.bottom - 24

    if (isOutsideViewport) {
      activeElement.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      })
    }
  }, [activeSegment?.id])

  const formattedProcessingDurationRemaining =
    useFormattedProcessingDuration(lastAiJobTranscript)

  if (!lastAiJobTranscript || lastAiJobTranscript?.status === 'pending') {
    return (
      <div className="transcript-pending">
        <div className="transcript-pending__skeletons">
          <div className="transcript-pending__skeletons__row">
            <Skeleton opacity={100} />
            <Skeleton opacity={100} />
          </div>
          <Skeleton opacity={75} />
          <Skeleton opacity={50} />
        </div>
        {formattedProcessingDurationRemaining ? (
          <div className="transcript-pending__message" role="alert">
            <img
              width={32}
              src="/assets/files/icons/pending-icon.svg"
              aria-hidden={true}
              alt={t('transcript.status.pending')}
            />
            <p>
              <Trans
                t={t}
                i18nKey="transcript.status.processingLong"
                values={{ value: formattedProcessingDurationRemaining }}
              >
                La transcription est en cours de génération et sera disponible
                dans <strong>tbd</strong>.
              </Trans>
            </p>
          </div>
        ) : (
          <Badge type="info">{t('transcript.status.pending')}</Badge>
        )}
      </div>
    )
  }

  return (
    <section
      className="recording-page__panel recording-page__panel--transcript"
      aria-label={t('transcript.title')}
    >
      {lastAiJobTranscript?.status === 'failed' && (
        <Badge type="danger">{t('transcript.status.failed')}</Badge>
      )}

      {transcriptQ.data &&
        transcriptSegments.length === 0 &&
        lastAiJobTranscript?.status === 'success' && (
          <Badge type="warning">{t('transcript.status.empty')}</Badge>
        )}

      {transcriptSegments.length > 0 && (
        <>
          <div
            className="transcript__transcript-list"
            ref={transcriptContainerRef}
            aria-label={t('transcript.segmentsAriaLabel')}
          >
            {transcriptSegments.map((segment, index) => (
              <Fragment key={segment.id}>
                <TranscriptSegment
                  isActive={index === activeSegmentIndex}
                  activeWordIndex={
                    index === activeSegmentIndex ? activeWordIndex : -1
                  }
                  segment={segment}
                  seekTo={seekTo}
                  setSegmentRef={setSegmentRef}
                />
                {/* "invisible" line break so that text selection works */}
                <div className="invisible-line-break"></div>
              </Fragment>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
