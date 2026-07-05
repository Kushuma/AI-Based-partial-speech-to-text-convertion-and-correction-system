import type { DashboardResponse, SessionSummary, TranscriptResponse, VocabularyItem } from "./types";

async function request<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Request failed.");
  }
  return (await response.json()) as T;
}

function extensionFromMimeType(mimeType: string): string {
  const normalized = mimeType.split(";")[0]?.trim().toLowerCase();
  if (normalized === "audio/ogg") {
    return ".ogg";
  }
  if (normalized === "audio/mp4" || normalized === "audio/m4a" || normalized === "audio/x-m4a") {
    return ".m4a";
  }
  if (normalized === "audio/mpeg" || normalized === "audio/mp3") {
    return ".mp3";
  }
  if (normalized === "audio/wav" || normalized === "audio/x-wav" || normalized === "audio/wave") {
    return ".wav";
  }
  return ".webm";
}

export function fetchDashboard(): Promise<DashboardResponse> {
  return request<DashboardResponse>("/api/dashboard");
}

export function createSession(): Promise<SessionSummary> {
  return request<SessionSummary>("/api/sessions", { method: "POST" });
}

export function uploadChunk(
  sessionId: string,
  blob: Blob,
  signal?: AbortSignal
): Promise<TranscriptResponse> {
  const form = new FormData();
  const extension = extensionFromMimeType(blob.type || "audio/webm");
  form.append("audio", blob, `chunk-${Date.now()}${extension}`);
  return request<TranscriptResponse>(`/api/sessions/${sessionId}/chunks`, {
    method: "POST",
    body: form,
    signal
  });
}

export function transcribeFile(file: File, signal?: AbortSignal): Promise<TranscriptResponse> {
  const form = new FormData();
  form.append("audio", file);
  return request<TranscriptResponse>("/api/transcribe-file", {
    method: "POST",
    body: form,
    signal
  });
}

export function createVocabulary(payload: {
  term: string;
  pronunciation_hint?: string;
  boost: number;
}): Promise<VocabularyItem> {
  return request<VocabularyItem>("/api/vocabulary", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export function deleteVocabulary(vocabId: number): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/vocabulary/${vocabId}`, {
    method: "DELETE"
  });
}
