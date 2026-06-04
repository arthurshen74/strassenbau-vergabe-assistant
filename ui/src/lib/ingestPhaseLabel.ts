// Maps an ingest pipeline phase (from IngestProgress.phase) to a user-facing label.
// Phase values mirror the backend IngestPhase enum.

const PHASE_LABELS: Record<string, string> = {
  ingest: 'Starting',
  thumbnails: 'Generating thumbnails',
  langchain: 'Indexing',
  extract: 'Extracting text',
  chunk: 'Indexing',
  lv: 'Parsing Leistungsverzeichnis',
};

export function ingestPhaseLabel(phase: string | undefined): string {
  return (phase && PHASE_LABELS[phase]) || 'Processing';
}
