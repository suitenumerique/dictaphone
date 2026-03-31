import { WhisperXResponse } from '@/features/ai-jobs/api/types.ts'

export type TranscriptWord = {
  text: string
  start: number
  end: number
  speaker: string | null
}

export type TranscriptViewSegment = {
  id: string
  text: string
  start: number
  end: number
  speaker: string | null
  words: TranscriptWord[]
}

/**
 * Transforms a WhisperXResponse object into an array of TranscriptViewSegment objects.
 *
 * @param {WhisperXResponse | undefined} transcript - The input transcript data containing segment and word-level information.
 * @return {TranscriptViewSegment[]} An array of transformed TranscriptViewSegment objects, or an empty array if no valid data is found.
 */
export function buildTranscriptViewSegments(
  transcript: WhisperXResponse | undefined
): TranscriptViewSegment[] {
  if (!transcript) return []

  if (transcript.segments.length > 0) {
    return transcript.segments
      .map((segment, index) => {
        const words =
          segment.words?.map((word) => ({
            text: word.word,
            start: word.start,
            end: word.end,
            speaker: word.speaker,
          })) ?? []

        return {
          id: `segment-${index}`,
          text: segment.text,
          start: segment.start,
          end: segment.end,
          speaker: segment.speaker,
          words,
        }
      })
      .filter(
        (segment) =>
          Number.isFinite(segment.start) && Number.isFinite(segment.end)
      )
  }

  if (transcript.word_segments.length > 0) {
    return transcript.word_segments.map((word, index) => ({
      id: `word-${index}`,
      text: word.word,
      start: word.start,
      end: word.end,
      speaker: word.speaker,
      words: [
        {
          text: word.word,
          start: word.start,
          end: word.end,
          speaker: word.speaker,
        },
      ],
    }))
  }

  return []
}

/**
 * Find the index of the segment that contains the current time.
 * @param segments Sorted array of segments
 * @param currentTime
 */
export function findActiveSegmentIndex(
  segments: { start: number; end: number }[],
  currentTime: number
): number {
  if (
    segments.length === 0 ||
    !Number.isFinite(currentTime) ||
    currentTime < 0
  ) {
    return -1
  }

  // Early return if the current time is within the first or last segment
  if (currentTime <= segments[0].start) return 0
  if (currentTime >= segments[segments.length - 1].end)
    return segments.length - 1

  // Binary search to find the segment containing the current time
  let low = 0
  let high = segments.length - 1

  while (low <= high) {
    const mid = Math.floor((low + high) / 2)
    const segment = segments[mid]

    if (currentTime < segment.start) {
      high = mid - 1
      continue
    }

    if (currentTime > segment.end) {
      low = mid + 1
      continue
    }

    return mid
  }

  return Math.max(0, high)
}

const TIMESTAMP_FORMATTER = new Intl.NumberFormat(undefined, {
  minimumIntegerDigits: 2,
  useGrouping: false,
})

export function formatTimestamp(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00'

  const roundedSeconds = Math.floor(seconds)
  const hours = Math.floor(roundedSeconds / 3600)
  const minutes = Math.floor((roundedSeconds % 3600) / 60)
  const remainingSeconds = roundedSeconds % 60

  if (hours > 0) {
    return `${TIMESTAMP_FORMATTER.format(hours)}:${TIMESTAMP_FORMATTER.format(minutes)}:${TIMESTAMP_FORMATTER.format(remainingSeconds)}`
  }

  return `${TIMESTAMP_FORMATTER.format(minutes)}:${TIMESTAMP_FORMATTER.format(remainingSeconds)}`
}
