import {
  useOpenInDocsMutation,
  useTranscript,
} from '@/features/ai-jobs/api/fetch.ts'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import {
  buildTranscriptViewSegments,
  findActiveSegmentIndex,
} from '@/features/ai-jobs/utils/transcript.ts'
import { ApiAiJob } from '@/features/ai-jobs/api/types.ts'
import { TranscriptSegment } from '@/features/recordings/components/TranscriptSegment.tsx'
import { useTranslation } from 'react-i18next'
import { Button } from '@gouvfr-lasuite/cunningham-react'

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
      variant="bordered"
      disabled={lastAiJobTranscript?.status !== 'success'}
      icon={<span className="material-icons">open_in_new</span>}
    >
      {t('transcript.openInDocsCta')}
    </Button>
  )
}

export function Transcript({
  lastAiJobTranscript,
  currentTime,
  seekTo,
}: {
  lastAiJobTranscript: ApiAiJob | null
  currentTime: number
  seekTo: (time: number) => void
}) {
  const { t } = useTranslation('recordings')
  const transcriptContainerRef = useRef<HTMLDivElement>(null)
  const segmentRefs = useRef<Map<string, HTMLButtonElement>>(new Map())

  const setSegmentRef = useCallback(
    (id: string, element: HTMLButtonElement | null) => {
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
    <section className="recording-page__panel recording-page__panel--transcript">
      <header className="recording-page__panel-header">
        <h2> {t('transcript.title')}</h2>
        {lastAiJobTranscript?.status === 'success' && (
          <OpenInDocsButton lastAiJobTranscript={lastAiJobTranscript} />
        )}
      </header>

      {lastAiJobTranscript?.status === 'failed' && (
        <div className="recording-page__state">
          {t('transcript.status.failed')}
        </div>
      )}

      {lastAiJobTranscript?.status === 'pending' && (
        <div className="recording-page__state">
          {t('transcript.status.pending')}
        </div>
      )}

      {transcriptQ.data &&
        transcriptSegments.length === 0 &&
        lastAiJobTranscript?.status === 'success' && (
          <div className="recording-page__state">
            {t('transcript.status.empty')}
          </div>
        )}

      {transcriptSegments.length > 0 && (
        <>
          <div
            className="transcript__transcript-list"
            ref={transcriptContainerRef}
          >
            {transcriptSegments.map((segment, index) => (
              <TranscriptSegment
                key={segment.id}
                isActive={index === activeSegmentIndex}
                activeWordIndex={
                  index === activeSegmentIndex ? activeWordIndex : -1
                }
                segment={segment}
                seekTo={seekTo}
                setSegmentRef={setSegmentRef}
              />
            ))}
          </div>
        </>
      )}
    </section>
  )
}
