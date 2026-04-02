export type ApiAiJob = {
  id: string | null // UUID
  type: 'transcript' | 'summary'
  status: 'pending' | 'success' | 'failed'
  created_at: string // ISO datetime string
  updated_at: string // ISO datetime string
}

export type ApiOpenInDocsResponse = {
  doc_url: string
}

export type WordSegment = {
  word: string
  start: number | null
  end: number | null
  score: number | null
  speaker: string | null
}

export type Segment = {
  start: number | null
  end: number | null
  text: string
  words: WordSegment[] | null
  speaker: string | null
}

export type WhisperXResponse = {
  segments: Segment[]
  word_segments: WordSegment[]
}
