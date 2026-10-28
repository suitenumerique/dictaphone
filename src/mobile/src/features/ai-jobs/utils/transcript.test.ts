import type { WhisperXResponse } from '@/features/ai-jobs/api/types.ts'
import { describe, expect, it } from 'vitest'
import {
  buildTranscriptViewSegments,
  findActiveSegmentIndex,
} from './transcript.ts'

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

describe('buildTranscriptViewSegments', () => {
  it.each(['SPEAKER_01', 'SPEAKER_02'])(
    'numbers paragraph speakers consecutively when %s has a word-only speaker',
    (mixedSpeaker) => {
      const transcript: WhisperXResponse = {
        segments: ['SPEAKER_01', 'SPEAKER_02', 'SPEAKER_01'].map(
          (speaker, index) => ({
            start: index * 5,
            end: index * 5 + 2,
            text: 'Hello there',
            speaker,
            words: [
              {
                word: 'Hello',
                start: index * 5,
                end: index * 5 + 1,
                score: 1,
                speaker: speaker === mixedSpeaker ? 'SPEAKER_00' : speaker,
              },
              {
                word: 'there',
                start: index * 5 + 1,
                end: index * 5 + 2,
                score: 1,
                speaker,
              },
            ],
          })
        ),
        word_segments: [],
      }

      const segments = buildTranscriptViewSegments(transcript)

      expect(segments.map((segment) => segment.speaker)).toEqual([
        '1',
        '2',
        '1',
      ])
      expect(segments.map((segment) => segment.words[1].speaker)).toEqual([
        '1',
        '2',
        '1',
      ])
      expect(
        segments.find(
          (segment) =>
            segment.speaker === (mixedSpeaker === 'SPEAKER_01' ? '1' : '2')
        )?.words[0].speaker
      ).toBe('3')
      expect(transcript.segments[0].speaker).toBe('SPEAKER_01')
    }
  )

  it('preserves missing speakers without reserving a participant number', () => {
    const segments = buildTranscriptViewSegments({
      segments: [null, 'SPEAKER_42', 'SPEAKER_10'].map((speaker, index) => ({
        start: index,
        end: index + 1,
        text: 'Hello',
        speaker,
        words: null,
      })),
      word_segments: [],
    })

    expect(segments.map((segment) => segment.speaker)).toEqual([null, '1', '2'])
  })
})
