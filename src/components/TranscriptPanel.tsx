import { SectionCard } from "./SectionCard";

interface TranscriptPanelProps {
  rawText: string;
  correctedText: string;
  status: string;
}

export function TranscriptPanel({ rawText, correctedText, status }: TranscriptPanelProps) {
  return (
    <SectionCard eyebrow="Output" title="Live transcript workspace">
      <div className="transcript-grid">
        <article className="transcript-block">
          <span className="transcript-block__label">Corrected text</span>
          <div
            className="transcript-block__body transcript-block__body--accent"
            data-testid="corrected-transcript"
          >
            {correctedText || "Corrected output will appear here as audio arrives."}
          </div>
        </article>
        <article className="transcript-block">
          <span className="transcript-block__label">Raw ASR transcript</span>
          <div className="transcript-block__body" data-testid="raw-transcript">
            {rawText || "Raw model output will appear here for traceability."}
          </div>
        </article>
      </div>
      <p className="muted-text">{status}</p>
    </SectionCard>
  );
}
