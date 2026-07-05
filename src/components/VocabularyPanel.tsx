import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { VocabularyItem } from "../lib/types";
import { SectionCard } from "./SectionCard";

interface VocabularyPanelProps {
  vocabulary: VocabularyItem[];
  onAdd: (payload: { term: string; pronunciation_hint?: string; boost: number }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

export function VocabularyPanel({ vocabulary, onAdd, onDelete }: VocabularyPanelProps) {
  const [term, setTerm] = useState("");
  const [pronunciationHint, setPronunciationHint] = useState("");

  return (
    <SectionCard eyebrow="Personalization" title="User vocabulary and term bias">
      <form
        className="vocabulary-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!term.trim()) {
            return;
          }
          await onAdd({
            term: term.trim(),
            pronunciation_hint: pronunciationHint.trim() || undefined,
            boost: 1.3
          });
          setTerm("");
          setPronunciationHint("");
        }}
      >
        <input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="Add preferred words, product names, people"
        />
        <input
          value={pronunciationHint}
          onChange={(event) => setPronunciationHint(event.target.value)}
          placeholder="Optional pronunciation hint"
        />
        <button className="ghost-button ghost-button--solid" type="submit">
          <Plus size={16} />
          <span>Add term</span>
        </button>
      </form>

      <div className="pill-list">
        {vocabulary.length ? (
          vocabulary.map((entry) => (
            <article key={entry.id} className="pill-card">
              <div>
                <strong>{entry.term}</strong>
                <span>{entry.pronunciation_hint || "No hint"}</span>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label={`Delete ${entry.term}`}
                onClick={() => onDelete(entry.id)}
              >
                <Trash2 size={15} />
              </button>
            </article>
          ))
        ) : (
          <p className="muted-text">
            Add vocabulary here to help the system preserve domain names and user-specific terms.
          </p>
        )}
      </div>
    </SectionCard>
  );
}

