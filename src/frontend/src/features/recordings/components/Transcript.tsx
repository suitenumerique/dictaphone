import { useTranscript } from '@/features/ai-jobs/api/fetch.ts'
import { Fragment, useCallback, useEffect, useMemo, useRef } from 'react'
import {
  buildTranscriptViewSegments,
  findActiveSegmentIndex,
  TranscriptViewSegment,
} from '@/features/ai-jobs/utils/transcript.ts'
import { ApiAiJob } from '@/features/ai-jobs/api/types.ts'
import { TranscriptSegment } from '@/features/recordings/components/TranscriptSegment.tsx'
import { useTranslation } from 'react-i18next'
import { Badge } from '@gouvfr-lasuite/ui-kit'

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

  return (
    <section
      className="recording-page__panel recording-page__panel--transcript"
      aria-label={t('transcript.title')}
    >
      {lastAiJobTranscript?.status === 'failed' && (
        <Badge type="danger">{t('transcript.status.failed')}</Badge>
      )}

      {lastAiJobTranscript?.status === 'pending' && (
        <Badge type="info">{t('transcript.status.pending')}</Badge>
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
