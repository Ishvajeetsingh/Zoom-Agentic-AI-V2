import { useEffect, useState, useCallback, useMemo } from "react";
import {
  Activity,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  RotateCcw,
  X,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Search,
  Filter,
  Heart,
} from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";
import { getProcessingRuns, retryProcessingRun, cancelProcessingRun } from "../api/processingRuns";
import { getQueueMetrics } from "../api/metrics";
import type { ProcessingRunListItem } from "../api/processingRuns";
import type { QueueMetrics } from "../api/metrics";

const PAGE_SIZE = 20;

type StatusFilter = "all" | "running" | "queued" | "failed" | "completed" | "completed_with_warnings" | "cancelled";
type SortField = "created_at" | "updated_at" | "priority";
type SortDir = "asc" | "desc";

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return "\u2014";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "\u2014";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const min = Math.floor(seconds / 60);
  const sec = Math.floor(seconds % 60);
  if (min < 60) return `${min}m ${sec}s`;
  const hr = Math.floor(min / 60);
  const rm = min % 60;
  return `${hr}h ${rm}m`;
}

function RunStatusBadge({ status }: { status: string }) {
  const n = status.toLowerCase();
  if (n === "completed")
    return (
      <span className="status-badge status-completed">
        <span className="status-badge-dot" />
        Completed
      </span>
    );
  if (n === "completed_with_warnings")
    return (
      <span className="status-badge status-warning">
        <span className="status-badge-dot" />
        With Warnings
      </span>
    );
  if (n === "failed")
    return (
      <span className="status-badge status-failed">
        <span className="status-badge-dot" />
        Failed
      </span>
    );
  if (n === "running" || n === "processing")
    return (
      <span className="status-badge status-in-progress">
        <span className="status-badge-dot" />
        Running
      </span>
    );
  if (n === "queued" || n === "pending")
    return (
      <span className="status-badge status-pending">
        <span className="status-badge-dot" />
        Queued
      </span>
    );
  if (n === "cancelled")
    return (
      <span className="status-badge status-pending">
        <span className="status-badge-dot" />
        Cancelled
      </span>
    );
  return (
    <span className="status-badge status-pending">
      <span className="status-badge-dot" />
      {status}
    </span>
  );
}

function HealthBar({ value, total, variant }: { value: number; total: number; variant: "success" | "warning" | "error" | "muted" }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  const colorMap = {
    success: "var(--c-success)",
    warning: "var(--c-warning)",
    error: "var(--c-error)",
    muted: "var(--c-muted-light)",
  };
  return (
    <div className="queue-health-bar-track">
      <div
        className="queue-health-bar-fill"
        style={{ width: `${pct}%`, background: colorMap[variant] }}
      />
    </div>
  );
}

export function QueuePage() {
  const [runs, setRuns] = useState<ProcessingRunListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortField, setSortField] = useState<SortField>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [queueMetrics, setQueueMetrics] = useState<QueueMetrics | null>(null);
  const [retrying, setRetrying] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");

  const loadQueue = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [runsRes, metricsRes] = await Promise.allSettled([
        getProcessingRuns({ limit: 100, order: sortDir }),
        getQueueMetrics(24),
      ]);
      if (runsRes.status === "fulfilled") {
        setRuns(runsRes.value.items);
        setTotal(runsRes.value.total);
      }
      if (metricsRes.status === "fulfilled") {
        setQueueMetrics(metricsRes.value);
      }
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load queue");
      setLoading(false);
    }
  }, [sortDir]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [runsRes, metricsRes] = await Promise.allSettled([
          getProcessingRuns({ limit: 100, order: sortDir }),
          getQueueMetrics(24),
        ]);
        if (cancelled) return;
        if (runsRes.status === "fulfilled") {
          setRuns(runsRes.value.items);
          setTotal(runsRes.value.total);
        }
        if (metricsRes.status === "fulfilled") {
          setQueueMetrics(metricsRes.value);
        }
        setLoading(false);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load queue");
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [sortDir]);

  const handleRetry = useCallback(async (runId: string) => {
    setRetrying((prev) => new Set(prev).add(runId));
    try {
      await retryProcessingRun(runId);
      setRuns((prev) =>
        prev.map((r) =>
          r.id === runId ? { ...r, status: "queued", retry_count: r.retry_count + 1 } : r
        )
      );
    } catch {
      // silently fail
    } finally {
      setRetrying((prev) => {
        const next = new Set(prev);
        next.delete(runId);
        return next;
      });
    }
  }, []);

  const handleCancel = useCallback(async (runId: string) => {
    try {
      await cancelProcessingRun(runId);
      setRuns((prev) =>
        prev.map((r) => (r.id === runId ? { ...r, status: "cancelled" } : r))
      );
    } catch {
      // silently fail
    }
  }, []);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const statusCounts = useMemo(() => {
    const counts = { all: runs.length, running: 0, queued: 0, failed: 0, completed: 0, completed_with_warnings: 0, cancelled: 0 };
    runs.forEach((r) => {
      const n = r.status.toLowerCase();
      if (n === "running" || n === "processing") counts.running++;
      else if (n === "queued" || n === "pending") counts.queued++;
      else if (n === "failed") counts.failed++;
      else if (n === "completed") counts.completed++;
      else if (n === "completed_with_warnings") counts.completed_with_warnings++;
      else if (n === "cancelled") counts.cancelled++;
    });
    return counts;
  }, [runs]);

  const filteredRuns = useMemo(() => {
    let list = runs;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (r) =>
          r.id.toLowerCase().includes(q) ||
          (r.transcript_id ?? "").toLowerCase().includes(q) ||
          (r.meeting_id ?? "").toLowerCase().includes(q)
      );
    }
    if (statusFilter !== "all") {
      list = list.filter((r) => {
        const n = r.status.toLowerCase();
        if (statusFilter === "running") return n === "running" || n === "processing";
        if (statusFilter === "queued") return n === "queued" || n === "pending";
        if (statusFilter === "completed") return n === "completed" || n === "completed_with_warnings";
        if (statusFilter === "completed_with_warnings") return n === "completed_with_warnings";
        return n === statusFilter;
      });
    }
    list = [...list].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortField === "priority") return (a.priority - b.priority) * dir;
      if (sortField === "updated_at") return ((new Date(a.updated_at)).getTime() - (new Date(b.updated_at)).getTime()) * dir;
      return ((new Date(a.created_at)).getTime() - (new Date(b.created_at)).getTime()) * dir;
    });
    return list;
  }, [runs, search, statusFilter, sortField, sortDir]);

  const pagedRuns = useMemo(() => {
    return filteredRuns.slice(offset, offset + PAGE_SIZE);
  }, [filteredRuns, offset]);

  const totalPages = Math.ceil(filteredRuns.length / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const successRate = queueMetrics?.success_rate;
  const successRateDisplay = successRate != null ? `${(successRate * 100).toFixed(1)}%` : "\u2014";
  const avgDuration = queueMetrics?.avg_duration_seconds;

  const healthStatus = useMemo(() => {
    if (!queueMetrics) return "unknown";
    const sr = queueMetrics.success_rate;
    const fl = queueMetrics.failed;
    if (sr != null && sr >= 0.9 && fl === 0) return "healthy";
    if (sr != null && sr >= 0.7) return "degraded";
    return "unhealthy";
  }, [queueMetrics]);

  const healthLabel: Record<string, string> = { healthy: "Healthy", degraded: "Degraded", unhealthy: "Unhealthy", unknown: "Unknown" };
  const healthVariant: Record<string, string> = { healthy: "success", degraded: "warning", unhealthy: "error", unknown: "muted" };

  return (
    <AppShell>
      <div className="queue-page">
        <div className="page-header">
          <h1>Processing Queue</h1>
          <p className="page-header-subtitle">Monitor and manage processing pipeline runs</p>
        </div>

        {loading && <LoadingState message="Loading queue..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <div className="queue-summary">
              <div className="queue-summary-card">
                <div className="queue-summary-icon queue-summary-icon-warning">
                  <Loader2 size={20} />
                </div>
                <div className="queue-summary-body">
                  <span className="queue-summary-value">{statusCounts.running}</span>
                  <span className="queue-summary-label">Running</span>
                </div>
              </div>
              <div className="queue-summary-card">
                <div className="queue-summary-icon queue-summary-icon-muted">
                  <Clock size={20} />
                </div>
                <div className="queue-summary-body">
                  <span className="queue-summary-value">{statusCounts.queued}</span>
                  <span className="queue-summary-label">Queued</span>
                </div>
              </div>
              <div className="queue-summary-card">
                <div className="queue-summary-icon queue-summary-icon-success">
                  <CheckCircle2 size={20} />
                </div>
                <div className="queue-summary-body">
                  <span className="queue-summary-value">{statusCounts.completed}</span>
                  <span className="queue-summary-label">Completed</span>
                </div>
              </div>
              <div className="queue-summary-card">
                <div className="queue-summary-icon queue-summary-icon-warning">
                  <AlertTriangle size={20} />
                </div>
                <div className="queue-summary-body">
                  <span className="queue-summary-value">{statusCounts.completed_with_warnings}</span>
                  <span className="queue-summary-label">With Warnings</span>
                </div>
              </div>
              <div className="queue-summary-card">
                <div className="queue-summary-icon queue-summary-icon-error">
                  <XCircle size={20} />
                </div>
                <div className="queue-summary-body">
                  <span className="queue-summary-value">{statusCounts.failed}</span>
                  <span className="queue-summary-label">Failed</span>
                </div>
              </div>
            </div>

            <section className="panel queue-panel">
              <div className="panel-header">
                <h2 className="panel-title">Queue Health</h2>
              </div>
              <div className="queue-health-row">
                <div className="queue-health-indicator">
                  <Heart size={16} className={`queue-health-heart queue-health-${healthVariant[healthStatus]}`} />
                  <span className={`queue-health-label queue-health-${healthVariant[healthStatus]}`}>
                    {healthLabel[healthStatus]}
                  </span>
                </div>
                <div className="queue-health-metrics">
                  <div className="queue-health-metric">
                    <span className="queue-health-metric-label">Success Rate</span>
                    <span className="queue-health-metric-value">{successRateDisplay}</span>
                    <HealthBar value={successRate ?? 0} total={1} variant={successRate != null && successRate >= 0.9 ? "success" : successRate != null && successRate >= 0.7 ? "warning" : "error"} />
                  </div>
                  <div className="queue-health-metric">
                    <span className="queue-health-metric-label">Avg Duration</span>
                    <span className="queue-health-metric-value">{formatDuration(avgDuration ?? null)}</span>
                  </div>
                  <div className="queue-health-metric">
                    <span className="queue-health-metric-label">Total Processed</span>
                    <span className="queue-health-metric-value">{queueMetrics?.total_runs ?? total}</span>
                  </div>
                  <div className="queue-health-metric">
                    <span className="queue-health-metric-label">Cancelled</span>
                    <span className="queue-health-metric-value">{queueMetrics?.cancelled ?? statusCounts.cancelled}</span>
                  </div>
                </div>
              </div>
              <div className="queue-health-bars">
                {total > 0 && (
                  <div className="queue-health-composition">
                    <HealthBar value={statusCounts.completed} total={total} variant="success" />
                    <HealthBar value={statusCounts.completed_with_warnings} total={total} variant="warning" />
                    <HealthBar value={statusCounts.running} total={total} variant="warning" />
                    <HealthBar value={statusCounts.failed} total={total} variant="error" />
                    <div className="queue-health-composition-labels">
                      <span className="queue-health-comp-item"><span className="queue-health-comp-dot" style={{ background: "var(--c-success)" }} />Completed {total > 0 ? ((statusCounts.completed / total) * 100).toFixed(0) : 0}%</span>
                      <span className="queue-health-comp-item"><span className="queue-health-comp-dot" style={{ background: "var(--c-warning)" }} />Warnings {total > 0 ? ((statusCounts.completed_with_warnings / total) * 100).toFixed(0) : 0}%</span>
                      <span className="queue-health-comp-item"><span className="queue-health-comp-dot" style={{ background: "var(--c-warning)" }} />Running {total > 0 ? ((statusCounts.running / total) * 100).toFixed(0) : 0}%</span>
                      <span className="queue-health-comp-item"><span className="queue-health-comp-dot" style={{ background: "var(--c-error)" }} />Failed {total > 0 ? ((statusCounts.failed / total) * 100).toFixed(0) : 0}%</span>
                    </div>
                  </div>
                )}
              </div>
            </section>

            <section className="panel queue-panel">
              <div className="queue-toolbar">
                <div className="queue-search-wrap">
                  <Search size={16} className="queue-search-icon" />
                  <input
                    type="text"
                    className="queue-search-input"
                    placeholder="Search by run ID, transcript, meeting..."
                    value={search}
                    onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
                  />
                </div>
                <div className="queue-filters">
                  <Filter size={14} className="queue-filter-icon" />
                  <select
                    className="filter-select"
                    value={statusFilter}
                    onChange={(e) => { setStatusFilter(e.target.value as StatusFilter); setOffset(0); }}
                  >
                    <option value="all">All Status ({statusCounts.all})</option>
                    <option value="running">Running ({statusCounts.running})</option>
                    <option value="queued">Queued ({statusCounts.queued})</option>
                    <option value="failed">Failed ({statusCounts.failed})</option>
                    <option value="completed">Completed ({statusCounts.completed})</option>
                    <option value="completed_with_warnings">With Warnings ({statusCounts.completed_with_warnings})</option>
                    <option value="cancelled">Cancelled ({statusCounts.cancelled})</option>
                  </select>
                </div>
              </div>

              {pagedRuns.length > 0 ? (
                <div style={{ overflowX: "auto" }}>
                  <table className="meeting-table queue-table">
                    <thead>
                      <tr>
                        <th>Run ID</th>
                        <th>Status</th>
                        <th>Priority</th>
                        <th>Attempt</th>
                        <th>
                          <button className="queue-th-btn" onClick={() => toggleSort("created_at")}>
                            Created
                            {sortField === "created_at" && <ArrowUpDown size={12} className="queue-sort-icon" />}
                          </button>
                        </th>
                        <th>Started</th>
                        <th>Completed</th>
                        <th>Linked Webhook</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedRuns.map((run) => {
                        const isFailed = run.status.toLowerCase() === "failed";
                        const isRunning = run.status.toLowerCase() === "running" || run.status.toLowerCase() === "processing";
                        const isActive = isRunning || run.status.toLowerCase() === "queued" || run.status.toLowerCase() === "pending";
                        const hasWarnings = run.status.toLowerCase() === "completed_with_warnings" || (run.warnings && run.warnings.length > 0);
                        return (
                          <tr key={run.id}>
                            <td className="queue-cell-id">
                              <a href={`#/transcripts/${run.transcript_id}`} className="queue-run-link">
                                {run.id.slice(0, 8)}
                              </a>
                            </td>
                            <td>
                              <RunStatusBadge status={run.status} />
                              {hasWarnings && run.warnings && run.warnings.length > 0 && (
                                <span className="queue-warning-count" title={run.warnings.join("; ")}>
                                  <AlertTriangle size={12} /> {run.warnings.length}
                                </span>
                              )}
                            </td>
                            <td className="cell-number">
                              <span className="queue-priority-badge">{run.priority}</span>
                            </td>
                            <td className="cell-number">
                               {run.retry_count}/{run.max_retries}
                            </td>
                            <td className="cell-date">{formatRelativeTime(run.created_at)}</td>
                            <td className="cell-date">{run.started_at ? formatRelativeTime(run.started_at) : "\u2014"}</td>
                            <td className="cell-date">{run.completed_at ? formatRelativeTime(run.completed_at) : "\u2014"}</td>
                            <td className="cell-date">
                              {run.webhook_event_id ? (
                                <a href="#/webhooks" className="queue-webhook-link">
                                  {run.webhook_event_id.slice(0, 8)}
                                </a>
                              ) : (
                                <span className="queue-none">&mdash;</span>
                              )}
                            </td>
                            <td>
                              <div className="queue-actions">
                                {isFailed && (
                                  <button
                                    className="queue-action-btn queue-action-retry"
                                    disabled={retrying.has(run.id)}
                                    onClick={() => handleRetry(run.id)}
                                    title="Retry"
                                  >
                                    <RotateCcw size={14} />
                                  </button>
                                )}
                                {isActive && (
                                  <button
                                    className="queue-action-btn queue-action-cancel"
                                    onClick={() => handleCancel(run.id)}
                                    title="Cancel"
                                  >
                                    <X size={14} />
                                  </button>
                                )}
                                {!isFailed && !isActive && (
                                  <span className="queue-none">&mdash;</span>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title="No Runs"
                  message={
                    search || statusFilter !== "all"
                      ? "No runs match your filters. Try adjusting your search."
                      : "No processing runs found. Process a meeting to create one."
                  }
                />
              )}

              {totalPages > 1 && (
                <div className="pagination queue-pagination">
                  <button
                    className="pagination-btn"
                    disabled={currentPage <= 1}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    <ChevronLeft size={16} />
                    Previous
                  </button>
                  <span className="pagination-info">
                    Page {currentPage} of {totalPages} &middot; {filteredRuns.length} runs
                  </span>
                  <button
                    className="pagination-btn"
                    disabled={currentPage >= totalPages}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    Next
                    <ChevronRight size={16} />
                  </button>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
