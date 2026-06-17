import { useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { getProcessingRuns } from "../../api/processingRuns";
import { getTranscripts } from "../../api/transcripts";
import type { TranscriptListItem } from "../../types/api";
import { CheckCircle, XCircle, Loader2, Clock, AlertTriangle } from "lucide-react";

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
  assessing: "Assessing",
  generating: "Generating",
  completed: "Completed",
  completed_with_warnings: "Completed (Warnings)",
  generation_failed: "Generation Failed",
  generating_learning_outputs: "Generating Learning",
  learning_generation_failed: "Learning Generation Failed",
  synthesizing: "Synthesizing",
  synthesis_failed: "Synthesis Failed",
  failed: "Failed",
};

function statusClass(status: string): string {
  if (status === "completed") return "status-completed";
  if (status === "completed_with_warnings") return "status-warning";
  if (status.endsWith("_failed") || status === "failed") return "status-failed";
  if (status.includes("_started") || status === "generating" || status === "assessing" || status === "generating_learning_outputs" || status === "synthesizing") return "status-in-progress";
  return "status-pending";
}

function statusIcon(status: string) {
  if (status === "completed") return <CheckCircle size={14} />;
  if (status === "completed_with_warnings") return <AlertTriangle size={14} />;
  if (status.endsWith("_failed") || status === "failed") return <XCircle size={14} />;
  if (status.includes("_started") || status === "generating" || status === "assessing" || status === "generating_learning_outputs" || status === "synthesizing") return <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />;
  return <Clock size={14} />;
}

function formatDate(iso: string | null): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleString();
}

export function RunTimeline() {
  const [transcripts, setTranscripts] = useState<TranscriptListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTranscripts({ limit: 50, order_by: "created_at", order: "desc" })
      .then((res: { items: TranscriptListItem[] }) => {
        if (!cancelled) {
          setTranscripts(res.items);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load processing runs");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <AppShell><LoadingState message="Loading runs..." /></AppShell>;
  if (error) return <AppShell><ErrorState message={error} /></AppShell>;
  if (transcripts.length === 0) return <AppShell><EmptyState message="No processing runs yet." title="No Runs" /></AppShell>;

  const completed = transcripts.filter((t) => t.status === "completed").length;
  const completedWithWarnings = transcripts.filter((t) => t.status === "completed_with_warnings").length;
  const failed = transcripts.filter((t) => t.status.endsWith("_failed") || t.status === "failed").length;
  const inProgress = transcripts.filter((t) => t.status.includes("_started") || t.status === "generating" || t.status === "assessing" || t.status === "generating_learning_outputs" || t.status === "synthesizing").length;

  return (
    <AppShell>
      <div className="page-header">
        <h1>Processing Runs</h1>
        <p className="page-header-subtitle">Track the status of transcript processing pipelines</p>
      </div>

      <div className="metrics-summary">
        <div className="metric-card">
          <div className="metric-icon-wrap metric-icon-primary">
            <Clock size={22} />
          </div>
          <div className="metric-body">
            <span className="metric-value">{transcripts.length}</span>
            <span className="metric-label">Total Runs</span>
          </div>
        </div>
        <div className="metric-card metric-card-success">
          <div className="metric-icon-wrap metric-icon-success">
            <CheckCircle size={22} />
          </div>
          <div className="metric-body">
            <span className="metric-value">{completed}</span>
            <span className="metric-label">Completed</span>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-icon-wrap metric-icon-warning">
            <AlertTriangle size={22} />
          </div>
          <div className="metric-body">
            <span className="metric-value">{completedWithWarnings}</span>
            <span className="metric-label">With Warnings</span>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-icon-wrap metric-icon-warning">
            <Loader2 size={22} />
          </div>
          <div className="metric-body">
            <span className="metric-value">{inProgress}</span>
            <span className="metric-label">In Progress</span>
          </div>
        </div>
        <div className="metric-card metric-card-error">
          <div className="metric-icon-wrap metric-icon-error">
            <XCircle size={22} />
          </div>
          <div className="metric-body">
            <span className="metric-value">{failed}</span>
            <span className="metric-label">Failed</span>
          </div>
        </div>
      </div>

      <div className="run-list-container">
        {transcripts.map((t) => (
          <a key={t.id} href={`#/transcripts/${t.id}`} style={{ textDecoration: "none", color: "inherit" }}>
            <div className="run-card">
              <div className="run-card-header">
                <span className="run-card-title">{t.transcript_filename ?? t.id}</span>
                <span className={`status-badge ${statusClass(t.status)}`}>
                  <span className="status-badge-dot" />
                  {STATUS_LABELS[t.status] ?? t.status}
                </span>
              </div>
              <div className="run-card-meta">
                <span className="run-card-meta-item">
                  {statusIcon(t.status)}
                  {STATUS_LABELS[t.status] ?? t.status}
                </span>
                <span className="run-card-meta-item">
                  <Clock size={12} />
                  {formatDate(t.created_at)}
                </span>
                <span className="run-card-meta-item">
                  Questions: {t.question_count ?? 0}
                </span>
                <span className="run-card-meta-item">
                  Chunks: {t.chunk_count ?? 0}
                </span>
              </div>
              {t.warnings && t.warnings.length > 0 && (
                <div className="run-card-warnings">
                  <AlertTriangle size={12} />
                  <span>{t.warnings.length} warning{t.warnings.length > 1 ? "s" : ""}</span>
                </div>
              )}
            </div>
          </a>
        ))}
      </div>
    </AppShell>
  );
}
