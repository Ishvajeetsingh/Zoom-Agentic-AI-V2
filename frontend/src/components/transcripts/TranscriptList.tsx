import type { TranscriptListItem } from "../../types/api";

interface TranscriptListProps {
  transcripts: TranscriptListItem[];
}

const STATUS_LABELS: Record<string, string> = {
  metadata_received: "Received",
  download_started: "Downloading",
  downloaded: "Downloaded",
  parsing_started: "Parsing",
  parsed: "Parsed",
  parsing_failed: "Parse Failed",
  cleaning_started: "Cleaning",
  cleaned: "Cleaned",
  cleaning_failed: "Clean Failed",
  chunking_started: "Chunking",
  chunked: "Chunked",
  chunking_failed: "Chunk Failed",
  generating: "Generating",
  completed: "Completed",
  generation_failed: "Generation Failed",
  failed: "Failed",
};

function statusClass(status: string): string {
  if (status === "completed") return "status-completed";
  if (status.endsWith("_failed") || status === "failed") return "status-failed";
  if (status.includes("_started") || status === "generating") return "status-in-progress";
  return "status-pending";
}

function formatDate(iso: string | null): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleString();
}

export function TranscriptList({ transcripts }: TranscriptListProps) {
  if (transcripts.length === 0) return null;

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="transcript-table">
        <thead>
          <tr>
            <th>Filename</th>
            <th>Status</th>
            <th>Questions</th>
            <th>Segments</th>
            <th>Chunks</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {transcripts.map((t) => (
            <tr key={t.id}>
              <td className="cell-filename">{t.transcript_filename ?? "\u2014"}</td>
              <td>
                <span className={`status-badge ${statusClass(t.status)}`}>
                  <span className="status-badge-dot" />
                  {STATUS_LABELS[t.status] ?? t.status}
                </span>
              </td>
              <td className="cell-number">{t.question_count ?? "\u2014"}</td>
              <td className="cell-number">{t.segment_count ?? "\u2014"}</td>
              <td className="cell-number">{t.chunk_count ?? "\u2014"}</td>
              <td className="cell-date">{formatDate(t.created_at)}</td>
              <td>
                <a href={`#/transcripts/${t.id}`} className="link-view">
                  View
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
