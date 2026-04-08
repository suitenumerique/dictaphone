import { describe, expect, it } from 'vitest'
import { findActiveSegmentIndex } from './transcript.ts'

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
