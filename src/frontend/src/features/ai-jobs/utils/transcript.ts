import { WhisperXResponse } from '@/features/ai-jobs/api/types.ts'

export type TranscriptWord = {
  text: string
  start: number | null
  end: number | null
  speaker: string | null
}

export type TranscriptViewSegment = {
  id: string
  text: string
  start: number | null
  end: number | null
  speaker: string | null
  words: TranscriptWord[]
}

const MAX_SEGMENT_DURATION = 60
function groupTranscriptSegments(
  segments: TranscriptViewSegment[]
): TranscriptViewSegment[] {
  if (segments.length === 0) return []

  const result: TranscriptViewSegment[] = []
  let current = { ...segments[0], words: [...segments[0].words] }

  for (let i = 1; i < segments.length; i++) {
    const seg = segments[i]
    const sameSpeaker = seg.speaker === current.speaker
    const currentStart = current.start ?? 0
    const segEnd = seg.end ?? seg.start ?? 0
    const withinDuration = segEnd - currentStart <= MAX_SEGMENT_DURATION

    if (sameSpeaker && withinDuration) {
      current = {
        ...current,
        text: current.text.trim() + ' ' + seg.text.trim(),
        end: seg.end,
        words: [...current.words, ...seg.words],
      }
    } else {
      result.push(current)
      current = { ...seg, words: [...seg.words] }
    }
  }

  result.push(current)
  return result
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

  // We need to fix the speaker from WhisperX
  const speakerMapped = new Map<string, string>()
  const getSpeaker = (speaker: string | null): string | null => {
    if (!speaker) return null

    if (!speakerMapped.has(speaker)) {
      speakerMapped.set(speaker, String(speakerMapped.size + 1))
    }

    return speakerMapped.get(speaker)!
  }

  if (transcript.segments.length > 0) {
    const segments = transcript.segments.map((segment, index) => {
      const words =
        segment.words?.map((word) => ({
          text: word.word,
          start: word.start,
          end: word.end,
          speaker: getSpeaker(word.speaker),
        })) ?? []

      return {
        id: `segment-${index}`,
        text: segment.text,
        start: segment.start,
        end: segment.end,
        speaker: getSpeaker(segment.speaker),
        words,
      }
    })

    return groupTranscriptSegments(segments)
  }

  if (transcript.word_segments.length > 0) {
    const segments = transcript.word_segments.map((word, index) => ({
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
    return groupTranscriptSegments(segments)
  }

  return []
}

/**
 * Find the index of the segment that contains the current time.
 * @param segments Sorted array of segments
 * @param currentTime
 */
export function findActiveSegmentIndex(
  segments: { start: number | null; end: number | null }[],
  currentTime: number
): number {
  if (!isFinite(currentTime) || currentTime < 0) return -1

  // Since we can have nulls as input data, dichotomic search is a bit tricky.
  // For now we will stick to a 0(n) search.

  let lastValidSegmentIdx = -1
  for (let idx = 0; idx < segments.length; idx++) {
    const segment = segments[idx]
    if (segment.start === null || segment.end === null) continue
    if (currentTime < segment.start) {
      return Math.max(lastValidSegmentIdx, 0)
    }
    if (segment.start <= currentTime && segment.end >= currentTime) {
      return idx
    }
    lastValidSegmentIdx = idx
  }
  return lastValidSegmentIdx
}

const TIMESTAMP_FORMATTER = new Intl.NumberFormat(undefined, {
  minimumIntegerDigits: 2,
  useGrouping: false,
})
const MAX_SUBTITLE_LINE_LENGTH = 36

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

export function buildTranscriptMarkdown({
  title,
  transcriptSegments,
  speakerLabel,
}: {
  title: string
  transcriptSegments: TranscriptViewSegment[]
  speakerLabel: string
}) {
  if (transcriptSegments.length === 0) {
    return null
  }

  let out = `# ${title}\n\n`
  transcriptSegments.forEach((segment) => {
    out += `**${formatTimestamp(segment.start ?? -1)} · ${speakerLabel} ${segment.speaker}** ${segment.text} \n\n`
  })

  return out.trim()
}

type SubtitleToken = {
  text: string
  start: number | null
  end: number | null
}

type SubtitleLine = {
  text: string
  tokens: SubtitleToken[]
}

/**
 * Normalize transcript text for subtitle processing.
 * Keeps punctuation intact while collapsing all whitespace.
 */
function normalizeSubtitleText(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

/**
 * Hard-wrap a single token if it exceeds the line budget.
 * Timing metadata is preserved on each split chunk.
 */
function splitLongToken(token: SubtitleToken, maxCharsPerLine: number) {
  if (token.text.length <= maxCharsPerLine) {
    return [token]
  }

  const out: SubtitleToken[] = []
  for (let i = 0; i < token.text.length; i += maxCharsPerLine) {
    out.push({
      ...token,
      text: token.text.slice(i, i + maxCharsPerLine),
    })
  }
  return out
}

/**
 * Build subtitle lines from a clause-like token slice while honoring
 * max character budget per line.
 */
function wrapClauseTokens(
  clauseTokens: SubtitleToken[],
  maxCharsPerLine: number
): SubtitleLine[] {
  const out: SubtitleLine[] = []
  let currentTokens: SubtitleToken[] = []
  let currentText = ''

  clauseTokens.forEach((token) => {
    const parts = splitLongToken(token, maxCharsPerLine)
    parts.forEach((part) => {
      if (!currentText) {
        currentTokens = [part]
        currentText = part.text
        return
      }

      const candidate = `${currentText} ${part.text}`
      if (candidate.length <= maxCharsPerLine) {
        currentTokens.push(part)
        currentText = candidate
      } else {
        out.push({ text: currentText, tokens: currentTokens })
        currentTokens = [part]
        currentText = part.text
      }
    })
  })

  if (currentText) {
    out.push({ text: currentText, tokens: currentTokens })
  }
  return out
}

/**
 * True when a line ends with strong sentence punctuation.
 * We use this as a preferred boundary for both line merges and screen changes.
 */
function endsSentence(text: string): boolean {
  return /[.!?]$/.test(text.trim())
}

/**
 * Split timed tokens into subtitle lines.
 * - Prefer splitting on punctuation tokens first
 * - Keep <= maxCharsPerLine
 * - Avoid merging after sentence-ending punctuation to keep sentence starts visible
 */
function splitTokensForSubtitles(
  tokens: SubtitleToken[],
  maxCharsPerLine: number
): SubtitleLine[] {
  if (tokens.length === 0) return []

  const clauses: SubtitleToken[][] = []
  let currentClause: SubtitleToken[] = []

  tokens.forEach((token) => {
    currentClause.push(token)
    if (/[.!?;:,]$/.test(token.text)) {
      clauses.push(currentClause)
      currentClause = []
    }
  })

  if (currentClause.length > 0) {
    clauses.push(currentClause)
  }

  const out: SubtitleLine[] = []
  clauses.forEach((clause) => {
    const wrapped = wrapClauseTokens(clause, maxCharsPerLine)
    wrapped.forEach((line) => {
      const previous = out.at(-1)
      if (!previous) {
        out.push(line)
        return
      }

      if (endsSentence(previous.text)) {
        out.push(line)
        return
      }

      const mergedText = `${previous.text} ${line.text}`
      if (mergedText.length <= maxCharsPerLine) {
        out[out.length - 1] = {
          text: mergedText,
          tokens: [...previous.tokens, ...line.tokens],
        }
      } else {
        out.push(line)
      }
    })
  })

  return out
}

/**
 * Paginate lines into subtitle "screens".
 * Target is 2 lines per screen, 3 lines only as an exceptional fallback.
 * When possible, force a page break right after a sentence-ending line.
 */
function paginateSubtitleLines(lines: SubtitleLine[]): SubtitleLine[][] {
  if (lines.length <= 2) {
    return [lines]
  }

  const pages: SubtitleLine[][] = []
  let cursor = 0

  while (cursor < lines.length) {
    const remaining = lines.length - cursor
    if (remaining <= 2) {
      pages.push(lines.slice(cursor))
      break
    }

    if (remaining === 3) {
      if (endsSentence(lines[cursor + 1].text)) {
        pages.push(lines.slice(cursor, cursor + 2))
        cursor += 2
      } else {
        pages.push(lines.slice(cursor, cursor + 3))
        cursor += 3
      }
      continue
    }

    if (endsSentence(lines[cursor].text)) {
      pages.push(lines.slice(cursor, cursor + 1))
      cursor += 1
      continue
    }

    pages.push(lines.slice(cursor, cursor + 2))
    cursor += 2
  }

  return pages
}

/**
 * Convert second-based timing into SRT timestamp format.
 */
function formatSrtTimestamp(seconds: number): string {
  const millisecondsTotal = Math.max(0, Math.round(seconds * 1000))
  const hours = Math.floor(millisecondsTotal / 3600000)
  const minutes = Math.floor((millisecondsTotal % 3600000) / 60000)
  const secs = Math.floor((millisecondsTotal % 60000) / 1000)
  const milliseconds = millisecondsTotal % 1000

  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')},${String(milliseconds).padStart(3, '0')}`
}

/**
 * Build timed subtitle tokens from a transcript segment.
 * Prefers `segment.words` because it contains precise word-level timing.
 */
function buildSubtitleTokens(segment: TranscriptViewSegment): SubtitleToken[] {
  if (segment.words.length > 0) {
    const words = segment.words
      .map((word) => ({
        text: normalizeSubtitleText(word.text),
        start: word.start,
        end: word.end,
      }))
      .filter((word) => Boolean(word.text))
    if (words.length > 0) {
      return words
    }
  }

  return normalizeSubtitleText(segment.text)
    .split(/\s+/)
    .filter(Boolean)
    .map((text) => ({
      text,
      start: null,
      end: null,
    }))
}

/**
 * Fallback duration estimate for cues that have no usable timing.
 */
function estimateDurationFromText(text: string): number {
  return Math.min(8, Math.max(1, text.length / 14))
}

/**
 * Type guard for optional numeric timings.
 */
function isFiniteNumber(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value)
}

/**
 * Compute cue start/end for a set of lines.
 * Uses word-level timing when present, then segment timing, then estimated timing.
 */
function getCueTimingsFromLines({
  lines,
  segment,
  previousEnd,
}: {
  lines: SubtitleLine[]
  segment: TranscriptViewSegment
  previousEnd: number
}) {
  const tokens = lines.flatMap((line) => line.tokens)
  const firstWordStart = tokens.find((token) => token.start !== null)?.start
  const lastWordEnd = [...tokens]
    .reverse()
    .find((token) => token.end !== null)?.end

  const fallbackStart = isFiniteNumber(segment.start)
    ? segment.start
    : previousEnd
  const start = isFiniteNumber(firstWordStart)
    ? Math.max(firstWordStart, previousEnd)
    : Math.max(fallbackStart, previousEnd)

  const fallbackEndCandidate = isFiniteNumber(segment.end)
    ? segment.end
    : start + estimateDurationFromText(lines.map((line) => line.text).join(' '))
  const end =
    isFiniteNumber(lastWordEnd) && lastWordEnd > start
      ? lastWordEnd
      : fallbackEndCandidate > start
        ? fallbackEndCandidate
        : start +
          estimateDurationFromText(lines.map((line) => line.text).join(' '))

  return { start, end }
}

export function buildTranscriptSrt(
  transcript: WhisperXResponse,
  { speakerLabel }: { speakerLabel: string }
): string | null {
  const transcriptSegments = buildTranscriptViewSegments(transcript)
  if (transcriptSegments.length === 0) {
    return null
  }

  const blocks: { start: number; end: number; lines: string[] }[] = []
  let previousEnd = 0
  let previousSpeaker: string | null = null

  transcriptSegments.forEach((segment) => {
    const includeSpeakerLabel =
      Boolean(segment.speaker) && segment.speaker !== previousSpeaker
    const tokens = buildSubtitleTokens(segment)
    const speakerToken = includeSpeakerLabel
      ? {
          text: `${speakerLabel} ${segment.speaker}:`,
          start: null,
          end: null,
        }
      : null
    const lines = splitTokensForSubtitles(
      speakerToken ? [speakerToken, ...tokens] : tokens,
      MAX_SUBTITLE_LINE_LENGTH
    )

    if (lines.length === 0) {
      return
    }

    const pages = paginateSubtitleLines(lines)

    pages.forEach((pageLines) => {
      const { start, end } = getCueTimingsFromLines({
        lines: pageLines,
        segment,
        previousEnd,
      })
      blocks.push({
        start,
        end,
        lines: pageLines.map((line) => line.text),
      })
      previousEnd = end
    })

    previousSpeaker = segment.speaker
  })

  if (blocks.length === 0) {
    return null
  }

  return blocks
    .map((block, index) => {
      return `${index + 1}\n${formatSrtTimestamp(block.start)} --> ${formatSrtTimestamp(block.end)}\n${block.lines.join('\n')}`
    })
    .join('\n\n')
}
