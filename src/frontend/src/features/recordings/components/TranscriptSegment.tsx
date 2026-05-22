import {
  formatTimestamp,
  TranscriptViewSegment,
} from '@/features/ai-jobs/utils/transcript.ts'
import { useTranslation } from 'react-i18next'
import { Fragment } from 'react'

const seekToSegmentStart = (
  segment: TranscriptViewSegment,
  seekTo: (seconds: number) => void
) => {
  if (segment.start !== null) {
    seekTo(segment.start)
  }
}

export function TranscriptSegment({
  segment,
  isActive,
  activeWordIndex,
  seekTo,
  setSegmentRef,
}: {
  segment: TranscriptViewSegment
  isActive: boolean
  activeWordIndex: number
  seekTo: (seconds: number) => void
  setSegmentRef: (id: string, element: HTMLSpanElement | null) => void
}) {
  const { t } = useTranslation('recordings')
  const segmentTimestamp = formatTimestamp(segment.start ?? -1)
  return (
    <span
      key={segment.id}
      className="transcript__segment"
      data-active={isActive}
      role="button"
      tabIndex={0}
      aria-label={t('transcript.segmentSeekAriaLabel', {
        timestamp: segmentTimestamp,
        speaker: segment.speaker
          ? `${t('transcript.speaker')} ${segment.speaker}`
          : t('transcript.noSpeaker'),
      })}
      onDoubleClick={(event) => {
        // We clear the selection to avoid a weird UX
        window.getSelection()?.removeAllRanges()
        if (event.target instanceof HTMLElement) {
          const wordElement =
            event.target.closest<HTMLElement>('[data-word-start]')
          const wordStart = wordElement?.dataset.wordStart
          if (wordStart) {
            seekTo(Number(wordStart))
            return
          }
        }
        seekToSegmentStart(segment, seekTo)
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Enter' && event.key !== ' ') {
          return
        }
        event.preventDefault()
        seekToSegmentStart(segment, seekTo)
      }}
      ref={(element) => setSegmentRef(segment.id, element)}
    >
      <span className="transcript__segment-text">
        <span className="transcript__intro">{segmentTimestamp}</span>
        {segment.speaker && (
          <span className={'transcript__intro'}>
            &nbsp;{`· ${t('transcript.speaker')} ${segment.speaker}`}
          </span>
        )}
        &nbsp;
        <span className="transcript__intro__spacer" />
        {segment.words.length > 0
          ? segment.words.map((word, wordIndex) => (
              <Fragment key={`${segment.id}-${wordIndex}-${word.start}`}>
                <span
                  className="transcript__word"
                  data-active={isActive && wordIndex === activeWordIndex}
                  data-word-start={word.start}
                >
                  {word.text}
                </span>
                <span className="transcript__word-whitespace">
                  {wordIndex < segment.words.length - 1 ? ' ' : ''}
                </span>
              </Fragment>
            ))
          : segment.text}
      </span>
    </span>
  )
}
