import { Upload, Mic, StopCircle } from "lucide-react";
import { SectionCard } from "./SectionCard";

interface RecorderPanelProps {
  levels: number[];
  isRecording: boolean;
  isLiveProcessing: boolean;
  supported: boolean;
  busy: boolean;
  onStart: () => void;
  onStop: () => void;
  onFilePicked: (file: File) => void;
}

export function RecorderPanel({
  levels,
  isRecording,
  isLiveProcessing,
  supported,
  busy,
  onStart,
  onStop,
  onFilePicked
}: RecorderPanelProps) {
  return (
    <SectionCard
      eyebrow="Capture"
      title="Record or upload speech"
      actions={
        <label className="ghost-button">
          <Upload size={16} />
          <span>Upload audio</span>
          <input
            type="file"
            accept="audio/*"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                onFilePicked(file);
              }
              event.currentTarget.value = "";
            }}
          />
        </label>
      }
    >
      <div className="recorder-panel">
        <div className="waveform">
          {levels.map((level, index) => (
            <span
              key={`${index}-${level}`}
              className={isRecording ? "waveform__bar waveform__bar--active" : "waveform__bar"}
              style={{ transform: `scaleY(${0.35 + level * 1.35})` }}
            />
          ))}
        </div>

        <div className="recorder-panel__cta">
          <div className="recorder-panel__actions">
            <button
              className="primary-button"
              type="button"
              onClick={onStart}
              disabled={busy || isRecording || !supported}
            >
              <Mic size={18} />
              <span>Start live capture</span>
            </button>
            <button
              className="ghost-button ghost-button--danger"
              type="button"
              data-testid="stop-live-capture"
              onClick={onStop}
              disabled={!isRecording}
            >
              <StopCircle size={18} />
              <span>Stop live capture</span>
            </button>
          </div>
          <p className="muted-text">
            {supported
              ? "Stop only ends microphone capture. Audio already captured will keep processing until the transcript finishes updating."
              : "This browser does not expose MediaRecorder. File upload is still available."}
          </p>
        </div>
      </div>
    </SectionCard>
  );
}

