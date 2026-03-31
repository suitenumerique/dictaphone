import {
  formatTimestamp,
  TranscriptViewSegment,
} from '@/features/ai-jobs/utils/transcript.ts'

function RenderSpeaker({ speaker }: { speaker: string | null }) {
  if (!speaker) return null
  if (speaker.match(/^SPEAKER_\d+$/)) {
    const speakerNumber = speaker.replace('SPEAKER_', '').replace('0', '')
    return (
      <div className="transcript__speaker">
        <span className="material-icons" aria-hidden="true">
          campaign
        </span>
        {speakerNumber}
      </div>
    )
  }
  return <span className="transcript__speaker">{speaker}</span>
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
  setSegmentRef: (id: string, element: HTMLButtonElement | null) => void
}) {
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
        seekTo(segment.start)
      }}
      ref={(element) => setSegmentRef(segment.id, element)}
    >
      <span className="transcript__segment-time">
        {formatTimestamp(segment.start)}
      </span>
      <span className="transcript__segment-content">
        <RenderSpeaker speaker={segment.speaker} />
        {segment.words.length > 0 ? (
          <span className="transcript__segment-text">
            {segment.words.map((word, wordIndex) => (
              <span
                key={`${segment.id}-${wordIndex}-${word.start}`}
                className="transcript__word"
                data-active={isActive && wordIndex === activeWordIndex}
                data-word-start={word.start}
              >
                {word.text}
              </span>
            ))}
          </span>
        ) : (
          <span className="transcript__segment-text">{segment.text}</span>
        )}
      </span>
    </button>
  )
}
