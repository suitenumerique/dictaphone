import {
  formatTimestamp,
  TranscriptViewSegment,
} from '@/features/ai-jobs/utils/transcript.ts'
import { useTranslation } from 'react-i18next'

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
  setSegmentRef: (id: string, element: HTMLButtonElement | null) => void
}) {
  const { t } = useTranslation('recordings')
  return (
    <button
      key={segment.id}
      className="transcript__segment"
      data-active={isActive}
      type="button"
      onClick={(event) => {
        if (event.target instanceof HTMLElement) {
          const wordElement =
            event.target.closest<HTMLElement>('[data-word-start]')
          const wordStart = wordElement?.dataset.wordStart
          if (wordStart) {
            seekTo(Number(wordStart))
            return
          }
        }
        if (segment.start !== null) {
          seekTo(segment.start)
        }
      }}
      ref={(element) => setSegmentRef(segment.id, element)}
    >
      <span className="transcript__segment-text">
        <span className="transcript__intro">
          {formatTimestamp(segment.start ?? -1)}
        </span>
        {segment.speaker && (
          <span className={'transcript__intro'}>
            &nbsp;{`· ${t('transcript.speaker')} ${segment.speaker}`}
          </span>
        )}
        <span className="transcript__intro__spacer" />
        {segment.words.length > 0
          ? segment.words.map((word, wordIndex) => (
              <span
                key={`${segment.id}-${wordIndex}-${word.start}`}
                className="transcript__word"
                data-active={isActive && wordIndex === activeWordIndex}
                data-word-start={word.start}
              >
                {word.text}
              </span>
            ))
          : segment.text}
      </span>
    </button>
  )
}
