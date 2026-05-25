import { describe, expect, it } from 'vitest'
import { buildTranscriptSrt, findActiveSegmentIndex } from './transcript.ts'

describe('findActiveSegmentIndex', () => {
  const segments: { start: number; end: number }[] = [
    {
      start: 0,
      end: 2,
    },
    {
      start: 3,
      end: 5,
    },
    {
      start: 6,
      end: 8,
    },
  ]

  it('returns -1 for empty segments', () => {
    expect(findActiveSegmentIndex([], 1)).toBe(-1)
  })

  it('returns -1 for invalid currentTime', () => {
    expect(findActiveSegmentIndex(segments, Number.NaN)).toBe(-1)
  })

  it('returns the first segment when currentTime is before or at the first start', () => {
    expect(findActiveSegmentIndex(segments, -1)).toBe(-1)
    expect(findActiveSegmentIndex(segments, 0)).toBe(0)
    expect(findActiveSegmentIndex(segments, 1)).toBe(0)
  })

  it('returns the correct segment in the middle', () => {
    expect(findActiveSegmentIndex(segments, 3)).toBe(1)
    expect(findActiveSegmentIndex(segments, 4)).toBe(1)
    expect(findActiveSegmentIndex(segments, 6.5)).toBe(2)
  })

  it('returns the last segment when currentTime is at or after the last end', () => {
    expect(findActiveSegmentIndex(segments, 8)).toBe(2)
    expect(findActiveSegmentIndex(segments, 10)).toBe(2)
  })

  it('returns the previous segment when currentTime is between segments', () => {
    expect(findActiveSegmentIndex(segments, 2.5)).toBe(0)
    expect(findActiveSegmentIndex(segments, 5.5)).toBe(1)
  })

  const trickySegments: { start: number | null; end: number | null }[] = [
    {
      start: 0,
      end: 2,
    },
    {
      start: null,
      end: null,
    },
    {
      start: null,
      end: null,
    },
    {
      start: 4,
      end: 5,
    },
    {
      start: null,
      end: null,
    },
    {
      start: 6,
      end: 8,
    },
  ]
  it('Works with tricky segment (null)', () => {
    expect(findActiveSegmentIndex(trickySegments, 2.5)).toBe(0)
    expect(findActiveSegmentIndex(trickySegments, 5.5)).toBe(3)
  })
})

describe('buildTranscriptSrt', () => {
  const parseSrtCues = (srt: string) =>
    srt
      .trim()
      .split('\n\n')
      .map((cue) => {
        const [index, timing, ...lines] = cue.split('\n')
        return { index, timing, lines }
      })

  it('wraps subtitles to 36 chars per line and max 3 lines per cue', () => {
    const srt = buildTranscriptSrt(
      {
        segments: [
          {
            start: 0,
            end: 10,
            speaker: 'SPEAKER_00',
            words: null,
            text: 'Hello everyone, this is a long subtitle sentence that should split on punctuation where possible, while keeping each line under the target limit.',
          },
        ],
        word_segments: [],
      },
      { speakerLabel: 'Speaker' }
    )

    expect(srt).not.toBeNull()

    const cues = parseSrtCues(srt!)
    expect(cues.length).toBeGreaterThan(0)

    cues.forEach((cue) => {
      const lines = cue.lines
      expect(lines.length).toBeLessThanOrEqual(3)
      lines.forEach((line) => {
        expect(line.length).toBeLessThanOrEqual(36)
      })
    })
  })

  it('adds translated speaker label only when the speaker changes', () => {
    const srt = buildTranscriptSrt(
      {
        segments: [
          {
            start: 0,
            end: 2,
            speaker: 'SPEAKER_10',
            words: [
              {
                word: 'Bonjour,',
                start: 0,
                end: 0.6,
                score: 1,
                speaker: 'SPEAKER_10',
              },
              {
                word: 'ça',
                start: 0.61,
                end: 0.9,
                score: 1,
                speaker: 'SPEAKER_10',
              },
              {
                word: 'va.',
                start: 0.91,
                end: 1.2,
                score: 1,
                speaker: 'SPEAKER_10',
              },
            ],
            text: 'Bonjour, ça va.',
          },
          {
            start: 2.1,
            end: 4,
            speaker: 'SPEAKER_10',
            words: [
              {
                word: 'Toujours',
                start: 2.2,
                end: 2.8,
                score: 1,
                speaker: 'SPEAKER_10',
              },
              {
                word: 'moi.',
                start: 2.81,
                end: 3.1,
                score: 1,
                speaker: 'SPEAKER_10',
              },
            ],
            text: 'Toujours moi.',
          },
          {
            start: 4.1,
            end: 6,
            speaker: 'SPEAKER_42',
            words: [
              {
                word: 'Changement',
                start: 4.2,
                end: 4.8,
                score: 1,
                speaker: 'SPEAKER_42',
              },
              {
                word: 'de',
                start: 4.81,
                end: 5.1,
                score: 1,
                speaker: 'SPEAKER_42',
              },
              {
                word: 'voix.',
                start: 5.11,
                end: 5.5,
                score: 1,
                speaker: 'SPEAKER_42',
              },
            ],
            text: 'Changement de voix.',
          },
        ],
        word_segments: [],
      },
      { speakerLabel: 'Intervenant' }
    )

    expect(srt).not.toBeNull()
    const mergedText = parseSrtCues(srt!)
      .flatMap((cue) => cue.lines)
      .join('\n')

    // speakers are remapped by buildTranscriptViewSegments: SPEAKER_10 -> 1, SPEAKER_42 -> 2
    expect(mergedText).toContain('Intervenant 1:')
    expect(mergedText).toContain('Intervenant 2:')
    expect(mergedText.match(/Intervenant 1:/g)?.length).toBe(1)
  })

  it('uses word timings for cue timestamps when words are available', () => {
    const srt = buildTranscriptSrt(
      {
        segments: [
          {
            start: 0,
            end: 20,
            speaker: 'SPEAKER_00',
            words: [
              {
                word: 'One',
                start: 1,
                end: 1.3,
                score: 1,
                speaker: 'SPEAKER_00',
              },
              {
                word: 'two',
                start: 1.31,
                end: 1.9,
                score: 1,
                speaker: 'SPEAKER_00',
              },
              {
                word: 'three.',
                start: 1.91,
                end: 2.4,
                score: 1,
                speaker: 'SPEAKER_00',
              },
            ],
            text: 'One two three.',
          },
        ],
        word_segments: [],
      },
      { speakerLabel: 'Speaker' }
    )

    expect(srt).not.toBeNull()
    const firstCue = parseSrtCues(srt!)[0]
    expect(firstCue.timing).toContain('00:00:01,000')
    expect(firstCue.timing).toContain('00:00:02,400')
  })

  it('falls back to estimated timing when no word timing is available', () => {
    const srt = buildTranscriptSrt(
      {
        segments: [
          {
            start: null,
            end: null,
            speaker: null,
            words: null,
            text: 'Fallback timing only.',
          },
        ],
        word_segments: [],
      },
      { speakerLabel: 'Speaker' }
    )

    expect(srt).not.toBeNull()
    const firstCue = parseSrtCues(srt!)[0]
    expect(firstCue.timing).toMatch(/^00:00:00,000 --> 00:00:0[1-8],\d{3}$/)
  })

  it('prefers screen changes after sentence-ending dots', () => {
    const srt = buildTranscriptSrt(
      {
        segments: [
          {
            start: 0,
            end: 12,
            speaker: null,
            words: null,
            text: 'First sentence is short. Second sentence is also short. Third sentence is also short. Fourth sentence is intentionally much longer so it wraps to additional subtitle lines.',
          },
        ],
        word_segments: [],
      },
      { speakerLabel: 'Speaker' }
    )

    expect(srt).not.toBeNull()
    const cues = parseSrtCues(srt!)
    expect(cues.length).toBeGreaterThan(1)
    expect(cues[0].lines).toHaveLength(1)
    expect(cues[0].lines[0].endsWith('.')).toBe(true)
    expect(cues[1].lines[0].startsWith('Second')).toBe(true)
  })
})
