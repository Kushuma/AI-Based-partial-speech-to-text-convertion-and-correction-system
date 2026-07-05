import type { AdaptiveParameter, SessionSummary } from "../lib/types";
import { SectionCard } from "./SectionCard";

interface SessionListProps {
  sessions: SessionSummary[];
  parameters: AdaptiveParameter[];
  onSelect: (session: SessionSummary) => void;
}

export function SessionList({ sessions, parameters, onSelect }: SessionListProps) {
  return (
    <SectionCard eyebrow="History" title="Recent sessions and adaptive state">
      <div className="session-list">
        {sessions.length ? (
          sessions.map((session) => (
            <button
              key={session.id}
              type="button"
              className="session-row"
              onClick={() => onSelect(session)}
            >
              <div>
                <strong>{session.corrected_transcript || "Untitled session"}</strong>
                <span>
                  {session.source.toUpperCase()} · {Math.round(session.avg_confidence * 100)}% ·{" "}
                  {new Date(session.updated_at).toLocaleTimeString()}
                </span>
              </div>
            </button>
          ))
        ) : (
          <p className="muted-text">No sessions yet. Start recording or upload an audio file.</p>
        )}
      </div>

      <div className="parameter-grid">
        {parameters.map((parameter) => (
          <div key={parameter.key} className="parameter-chip">
            <span>{parameter.key}</span>
            <strong>{parameter.value}</strong>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}
