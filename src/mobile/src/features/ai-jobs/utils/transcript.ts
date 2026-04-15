import { WhisperXResponse } from '@/features/ai-jobs/api/types.ts';

export type TranscriptWord = {
  text: string;
  start: number | null;
  end: number | null;
  speaker: string | null;
};

export type TranscriptViewSegment = {
  id: string;
  text: string;
  start: number | null;
  end: number | null;
  speaker: string | null;
  words: TranscriptWord[];
};

/**
 * Transforms a WhisperXResponse object into an array of TranscriptViewSegment objects.
 *
 * @param {WhisperXResponse | undefined} transcript - The input transcript data containing segment and word-level information.
 * @return {TranscriptViewSegment[]} An array of transformed TranscriptViewSegment objects, or an empty array if no valid data is found.
 */
export function buildTranscriptViewSegments(
  transcript: WhisperXResponse | undefined,
): TranscriptViewSegment[] {
  if (!transcript) return [];

  // We need to fix the speaker from WhisperX
  const speakerMapped = new Map<string, string>();
  const getSpeaker = (speaker: string | null): string | null => {
    if (!speaker) return null;

    if (!speakerMapped.has(speaker)) {
      speakerMapped.set(speaker, String(speakerMapped.size + 1));
    }

    return speakerMapped.get(speaker)!;
  };

  if (transcript.segments.length > 0) {
    return transcript.segments.map((segment, index) => {
      const words =
        segment.words?.map(word => ({
          text: word.word,
          start: word.start,
          end: word.end,
          speaker: getSpeaker(word.speaker),
        })) ?? [];

      return {
        id: `segment-${index}`,
        text: segment.text,
        start: segment.start,
        end: segment.end,
        speaker: getSpeaker(segment.speaker),
        words,
      };
    });
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
    }));
  }

  return [];
}

/**
 * Find the index of the segment that contains the current time.
 * @param segments Sorted array of segments
 * @param currentTime
 */
export function findActiveSegmentIndex(
  segments: { start: number | null; end: number | null }[],
  currentTime: number,
): number {
  if (!isFinite(currentTime) || currentTime < 0) return -1;

  // Since we can have nulls as input data, dichotomic search is a bit tricky.
  // For now we will stick to a 0(n) search.

  let lastValidSegmentIdx = -1;
  for (let idx = 0; idx < segments.length; idx++) {
    const segment = segments[idx];
    if (segment.start === null || segment.end === null) continue;
    if (currentTime < segment.start) {
      return Math.max(lastValidSegmentIdx, 0);
    }
    if (segment.start <= currentTime && segment.end >= currentTime) {
      return idx;
    }
    lastValidSegmentIdx = idx;
  }
  return lastValidSegmentIdx;
}

const TIMESTAMP_FORMATTER = new Intl.NumberFormat(undefined, {
  minimumIntegerDigits: 2,
  useGrouping: false,
});

export function formatTimestamp(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00';

  const roundedSeconds = Math.floor(seconds);
  const hours = Math.floor(roundedSeconds / 3600);
  const minutes = Math.floor((roundedSeconds % 3600) / 60);
  const remainingSeconds = roundedSeconds % 60;

  if (hours > 0) {
    return `${TIMESTAMP_FORMATTER.format(hours)}:${TIMESTAMP_FORMATTER.format(
      minutes,
    )}:${TIMESTAMP_FORMATTER.format(remainingSeconds)}`;
  }

  return `${TIMESTAMP_FORMATTER.format(minutes)}:${TIMESTAMP_FORMATTER.format(
    remainingSeconds,
  )}`;
}
