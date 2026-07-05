interface MetricsStripProps {
  confidence: number;
  durationSeconds: number;
  chunkCount: number;
  processingMs: number;
}

export function MetricsStrip({
  confidence,
  durationSeconds,
  chunkCount,
  processingMs
}: MetricsStripProps) {
  const metrics = [
    {
      label: "Confidence",
      value: `${Math.round(confidence * 100)}%`
    },
    {
      label: "Audio captured",
      value: `${durationSeconds.toFixed(1)}s`
    },
    {
      label: "Chunk revisions",
      value: String(chunkCount)
    },
    {
      label: "Latest process time",
      value: `${processingMs} ms`
    }
  ];

  return (
    <div className="metrics-strip">
      {metrics.map((metric) => (
        <article key={metric.label} className="metric-tile">
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </article>
      ))}
    </div>
  );
}

