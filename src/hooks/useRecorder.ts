import { useCallback, useEffect, useRef, useState } from "react";

const LEVEL_COUNT = 20;

function preferredMimeType(): string | undefined {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus"
  ];

  return candidates.find((value) => MediaRecorder.isTypeSupported(value));
}

export function useRecorder(onChunk: (chunk: Blob) => void) {
  const [isRecording, setIsRecording] = useState(false);
  const [levels, setLevels] = useState<number[]>(Array.from({ length: LEVEL_COUNT }, () => 0.16));

  const emitChunksRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);

  const stopVisualization = useCallback(() => {
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    setLevels(Array.from({ length: LEVEL_COUNT }, (_, index) => 0.12 + ((index % 3) * 0.03)));
  }, []);

  const startVisualization = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) {
      return;
    }

    const buffer = new Uint8Array(analyser.frequencyBinCount);

    const tick = () => {
      analyser.getByteFrequencyData(buffer);
      const nextLevels = Array.from({ length: LEVEL_COUNT }, (_, index) => {
        const start = Math.floor((index / LEVEL_COUNT) * buffer.length);
        const end = Math.max(start + 1, Math.floor(((index + 1) / LEVEL_COUNT) * buffer.length));
        let total = 0;
        for (let cursor = start; cursor < end; cursor += 1) {
          total += buffer[cursor] ?? 0;
        }
        const avg = total / (end - start);
        return Math.max(0.12, avg / 255);
      });
      setLevels(nextLevels);
      animationRef.current = requestAnimationFrame(tick);
    };

    animationRef.current = requestAnimationFrame(tick);
  }, []);

  const stop = useCallback((options?: { discardPendingChunk?: boolean }) => {
    const discardPendingChunk = options?.discardPendingChunk ?? true;
    emitChunksRef.current = !discardPendingChunk;

    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    audioContextRef.current?.close();
    audioContextRef.current = null;
    analyserRef.current = null;
    setIsRecording(false);
    stopVisualization();
  }, [stopVisualization]);

  const start = useCallback(async () => {
    if (isRecording) {
      return;
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });

    streamRef.current = stream;
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    audioContextRef.current = audioContext;
    analyserRef.current = analyser;

    const mimeType = preferredMimeType();
    const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

    recorder.ondataavailable = (event) => {
      if (emitChunksRef.current && event.data && event.data.size > 0) {
        onChunk(event.data);
      }
    };
    recorder.onstop = () => {
      emitChunksRef.current = false;
      setIsRecording(false);
      stopVisualization();
    };
    emitChunksRef.current = true;
    recorder.start(4000);
    recorderRef.current = recorder;
    setIsRecording(true);
    startVisualization();
  }, [isRecording, onChunk, startVisualization, stopVisualization]);

  useEffect(() => {
    return () => stop();
  }, [stop]);

  return {
    isRecording,
    levels,
    start,
    stop,
    supported:
      typeof window !== "undefined" &&
      typeof navigator !== "undefined" &&
      !!navigator.mediaDevices &&
      typeof MediaRecorder !== "undefined"
  };
}
