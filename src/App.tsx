import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Sparkles, Cpu, ShieldCheck, Hourglass } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import {
  createSession,
  createVocabulary,
  deleteVocabulary,
  fetchDashboard,
  transcribeFile,
  uploadChunk
} from "./lib/api";
import type {
  DashboardResponse,
  SessionSummary,
  TranscriptResponse,
  VocabularyItem
} from "./lib/types";
import { useRecorder } from "./hooks/useRecorder";
import { AmbientBackdrop } from "./components/AmbientBackdrop";
import { MetricsStrip } from "./components/MetricsStrip";
import { RecorderPanel } from "./components/RecorderPanel";
import { SessionList } from "./components/SessionList";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { VocabularyPanel } from "./components/VocabularyPanel";

const emptyDashboard: DashboardResponse = {
  sessions: [],
  vocabulary: [],
  parameters: []
};

interface QueuedChunk {
  blob: Blob;
  pipelineId: number;
}

export function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(emptyDashboard);
  const [status, setStatus] = useState("Ready. Start a live session or upload audio.");
  const [activeSession, setActiveSession] = useState<SessionSummary | null>(null);
  const [rawText, setRawText] = useState("");
  const [correctedText, setCorrectedText] = useState("");
  const [confidence, setConfidence] = useState(0);
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [chunkCount, setChunkCount] = useState(0);
  const [processingMs, setProcessingMs] = useState(0);
  const [isLiveProcessing, setIsLiveProcessing] = useState(false);
  const [isFileUploading, setIsFileUploading] = useState(false);

  const activeSessionIdRef = useRef<string | null>(null);
  const queueRef = useRef<QueuedChunk[]>([]);
  const flushingRef = useRef(false);
  const livePipelineIdRef = useRef(0);
  const liveAbortControllerRef = useRef<AbortController | null>(null);

  const busy = isLiveProcessing || isFileUploading;

  const refreshDashboard = useCallback(async () => {
    const next = await fetchDashboard();
    setDashboard(next);
    if (activeSessionIdRef.current) {
      const current = next.sessions.find((session) => session.id === activeSessionIdRef.current);
      if (current) {
        setActiveSession(current);
      }
    }
  }, []);

  useEffect(() => {
    void refreshDashboard().catch((error: Error) => {
      setStatus(`Unable to load dashboard: ${error.message}`);
    });
  }, [refreshDashboard]);

  const applyTranscript = useCallback((result: TranscriptResponse) => {
    activeSessionIdRef.current = result.session.id;
    setActiveSession(result.session);
    setRawText(result.raw_transcript);
    setCorrectedText(result.corrected_transcript);
    setConfidence(result.avg_confidence);
    setDurationSeconds(result.duration_seconds);
    setChunkCount(result.chunk_count);
    setProcessingMs(result.processing_ms);
  }, []);

  const ensureLiveSession = useCallback(async (pipelineId: number) => {
    if (activeSessionIdRef.current) {
      return activeSessionIdRef.current;
    }
    const created = await createSession();
    if (pipelineId === livePipelineIdRef.current) {
      activeSessionIdRef.current = created.id;
      setActiveSession(created);
    }
    return created.id;
  }, []);

  const flushQueue = useCallback(async () => {
    if (flushingRef.current) {
      return;
    }

    flushingRef.current = true;
    try {
      while (true) {
        const pipelineId = livePipelineIdRef.current;
        const nextChunkIndex = queueRef.current.findIndex((item) => item.pipelineId === pipelineId);
        if (nextChunkIndex === -1) {
          break;
        }

        const [nextChunk] = queueRef.current.splice(nextChunkIndex, 1);
        if (!nextChunk || nextChunk.pipelineId !== livePipelineIdRef.current) {
          continue;
        }

        const sessionId = await ensureLiveSession(nextChunk.pipelineId);
        if (nextChunk.pipelineId !== livePipelineIdRef.current) {
          break;
        }

        setStatus("Processing the next live chunk on the local CPU pipeline.");
        setIsLiveProcessing(true);
        const controller = new AbortController();
        liveAbortControllerRef.current = controller;

        try {
          const result = await uploadChunk(sessionId, nextChunk.blob, controller.signal);
          if (nextChunk.pipelineId !== livePipelineIdRef.current) {
            break;
          }
          applyTranscript(result);
        } catch (error) {
          if (controller.signal.aborted) {
            break;
          }
          throw error;
        } finally {
          if (liveAbortControllerRef.current === controller) {
            liveAbortControllerRef.current = null;
          }
        }

        setStatus("Transcript revised successfully from the latest audio chunk.");
      }
    } catch (error) {
      setStatus(`Live processing failed: ${(error as Error).message}`);
    } finally {
      flushingRef.current = false;
      const hasQueuedChunks = queueRef.current.some(
        (item) => item.pipelineId === livePipelineIdRef.current
      );
      setIsLiveProcessing(hasQueuedChunks || liveAbortControllerRef.current !== null);
      await refreshDashboard().catch(() => {});
      if (hasQueuedChunks) {
        void flushQueue();
      }
    }
  }, [applyTranscript, ensureLiveSession, refreshDashboard]);

  const { isRecording, levels, start, stop, supported } = useRecorder((chunk) => {
    queueRef.current.push({ blob: chunk, pipelineId: livePipelineIdRef.current });
    setIsLiveProcessing(true);
    void flushQueue();
  });

  const resetLivePipeline = useCallback(() => {
    livePipelineIdRef.current += 1;
    queueRef.current = [];
    liveAbortControllerRef.current?.abort();
    liveAbortControllerRef.current = null;
    setIsLiveProcessing(false);
    stop({ discardPendingChunk: true });
  }, [stop]);

  const stopLiveCapture = useCallback(() => {
    if (!isRecording) {
      setStatus("Live capture is already stopped.");
      return;
    }

    stop({ discardPendingChunk: false });
    setStatus("Live capture stopped. Processing the captured audio that is already queued.");
  }, [isRecording, stop]);

  const handleFilePicked = useCallback(
    async (file: File) => {
      if (isRecording || isLiveProcessing) {
        resetLivePipeline();
      }

      setIsFileUploading(true);
      setStatus(`Uploading ${file.name} for full local transcription.`);
      try {
        const result = await transcribeFile(file);
        applyTranscript(result);
        setStatus("Upload processed successfully. Corrected output is ready.");
        await refreshDashboard();
      } catch (error) {
        setStatus(`File transcription failed: ${(error as Error).message}`);
      } finally {
        setIsFileUploading(false);
      }
    },
    [applyTranscript, isLiveProcessing, isRecording, refreshDashboard, resetLivePipeline]
  );

  const handleAddVocabulary = useCallback(
    async (payload: { term: string; pronunciation_hint?: string; boost: number }) => {
      const created = await createVocabulary(payload);
      setDashboard((current) => ({
        ...current,
        vocabulary: [created, ...current.vocabulary.filter((item) => item.id !== created.id)]
      }));
      setStatus(`Vocabulary term "${created.term}" saved for future biasing.`);
    },
    []
  );

  const handleDeleteVocabulary = useCallback(async (id: number) => {
    await deleteVocabulary(id);
    setDashboard((current) => ({
      ...current,
      vocabulary: current.vocabulary.filter((entry) => entry.id !== id)
    }));
    setStatus("Vocabulary term removed.");
  }, []);

  const handleSelectSession = useCallback((session: SessionSummary) => {
    activeSessionIdRef.current = session.id;
    setActiveSession(session);
    setRawText(session.raw_transcript);
    setCorrectedText(session.corrected_transcript);
    setConfidence(session.avg_confidence);
    setDurationSeconds(session.duration_seconds);
    setChunkCount(session.chunk_count);
    setProcessingMs(session.processing_ms);
    setStatus("Loaded a previous session from local history.");
  }, []);

  const summaryCards = useMemo(
    () => [
      {
        icon: Cpu,
        title: "CPU-only pipeline",
        body: "Whisper ASR, cleanup, correction, and persistence are all pinned to CPU execution."
      },
      {
        icon: ShieldCheck,
        title: "Local-first processing",
        body: "Audio stays on this machine. Sessions, vocabulary, and adaptive state are stored locally."
      },
      {
        icon: Hourglass,
        title: "Accuracy over speed",
        body: "The pipeline reprocesses accumulated audio to improve output as more speech arrives."
      }
    ],
    []
  );

  return (
    <div className="app-shell">
      <AmbientBackdrop />
      <main className="app-shell__content">
        <motion.header
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="hero"
        >
          <div className="hero__copy">
            <p className="hero__eyebrow">
              <Sparkles size={15} />
              <span>Speech Repair Studio</span>
            </p>
            <h1>High-fidelity correction for partial, noisy, and broken speech.</h1>
            <p className="hero__body">
              A local CPU-first workflow that captures live audio, revises transcripts continuously,
              preserves preferred vocabulary, and stores history for later review.
            </p>
          </div>
          <div className="hero__badges">
            {summaryCards.map((item) => {
              const Icon = item.icon;
              return (
                <article key={item.title} className="hero-badge">
                  <div className="hero-badge__icon">
                    <Icon size={18} />
                  </div>
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.body}</span>
                  </div>
                </article>
              );
            })}
          </div>
        </motion.header>

        <MetricsStrip
          confidence={confidence}
          durationSeconds={durationSeconds}
          chunkCount={chunkCount}
          processingMs={processingMs}
        />

        <div className="app-grid">
          <div className="app-grid__main">
            <RecorderPanel
              levels={levels}
              isRecording={isRecording}
              isLiveProcessing={isLiveProcessing}
              supported={supported}
              busy={busy}
              onStart={() => {
                resetLivePipeline();
                activeSessionIdRef.current = null;
                setActiveSession(null);
                setRawText("");
                setCorrectedText("");
                setConfidence(0);
                setDurationSeconds(0);
                setChunkCount(0);
                setProcessingMs(0);
                setIsLiveProcessing(false);
                setStatus("Live capture started. Waiting for the first audio chunk.");
                void start().catch((error: Error) => {
                  setStatus(`Microphone access failed: ${error.message}`);
                });
              }}
              onStop={stopLiveCapture}
              onFilePicked={(file) => {
                void handleFilePicked(file);
              }}
            />

            <TranscriptPanel
              rawText={rawText}
              correctedText={correctedText}
              status={status}
            />

            <VocabularyPanel
              vocabulary={dashboard.vocabulary}
              onAdd={handleAddVocabulary}
              onDelete={handleDeleteVocabulary}
            />
          </div>

          <div className="app-grid__side">
            <SessionList
              sessions={dashboard.sessions}
              parameters={dashboard.parameters}
              onSelect={handleSelectSession}
            />

            <motion.section
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, delay: 0.1 }}
              className="status-panel"
            >
              <span className="status-panel__label">Current session</span>
              <strong>{activeSession?.id ?? "Not started"}</strong>
              <p>
                {activeSession
                  ? `${activeSession.source.toUpperCase()} source Â· ${Math.round(
                      activeSession.avg_confidence * 100
                    )}% average confidence`
                  : "No active session selected yet."}
              </p>
            </motion.section>
          </div>
        </div>

        <AnimatePresence>
          {busy ? (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 12 }}
              className="floating-status"
            >
              Processing audio locally...
            </motion.div>
          ) : null}
        </AnimatePresence>
      </main>
    </div>
  );
}

