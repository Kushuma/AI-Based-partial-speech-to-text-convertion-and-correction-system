export interface SessionSummary {
  id: string;
  source: string;
  status: string;
  created_at: string;
  updated_at: string;
  raw_transcript: string;
  corrected_transcript: string;
  avg_confidence: number;
  duration_seconds: number;
  processing_ms: number;
  chunk_count: number;
  language: string | null;
}

export interface VocabularyItem {
  id: number;
  term: string;
  pronunciation_hint: string | null;
  boost: number;
  usage_count: number;
  created_at: string;
}

export interface AdaptiveParameter {
  key: string;
  value: string;
  updated_at: string;
}

export interface WordConfidence {
  word: string;
  start: number;
  end: number;
  probability: number;
}

export interface TranscriptResponse {
  session: SessionSummary;
  raw_transcript: string;
  corrected_transcript: string;
  avg_confidence: number;
  duration_seconds: number;
  processing_ms: number;
  chunk_count: number;
  words: WordConfidence[];
}

export interface DashboardResponse {
  sessions: SessionSummary[];
  vocabulary: VocabularyItem[];
  parameters: AdaptiveParameter[];
}

