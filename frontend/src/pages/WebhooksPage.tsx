import { useEffect, useState, useCallback, useMemo } from "react";
import {
  Webhook,
  CheckCircle2,
  XCircle,
  Clock,
  Search,
  Filter,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Activity,
  AlertTriangle,
} from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";
import { getWebhookEvents } from "../api/webhooks";
import { getWebhookEventStatusCounts } from "../api/metrics";
import { getProcessingRuns } from "../api/processingRuns";
import type { WebhookEventListItem } from "../api/webhooks";
import type { ProcessingRunListItem } from "../api/processingRuns";

const PAGE_SIZE = 20;

type StatusFilter = "all" | "processed" | "pending" | "failed";
type SortField = "received_at" | "event_type" | "status";
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

function formatDateTime(iso: string | null): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function WebhookStatusBadge({ status }: { status: string }) {
  const n = status.toLowerCase();
  if (n === "processed" || n === "completed")
    return (
      <span className="status-badge status-completed">
        <span className="status-badge-dot" />
        Processed
      </span>
    );
  if (n === "failed" || n === "error")
    return (
      <span className="status-badge status-failed">
        <span className="status-badge-dot" />
        Failed
      </span>
    );
  if (n === "pending" || n === "received")
    return (
      <span className="status-badge status-pending">
        <span className="status-badge-dot" />
        Pending
      </span>
    );
  return (
    <span className="status-badge status-pending">
      <span className="status-badge-dot" />
      {status}
    </span>
  );
}

function EventTypeBadge({ eventType }: { eventType: string }) {
  const n = eventType.toLowerCase();
  let variant = "default";
  if (n.includes("recording")) variant = "recording";
  else if (n.includes("meeting") || n.includes(" webinar")) variant = "meeting";
  else if (n.includes("participant")) variant = "participant";

  return (
    <span className={`webhook-event-type-badge webhook-event-type-${variant}`}>
      {eventType.replace(/_/g, " ")}
    </span>
  );
}

export function WebhooksPage() {
  const [webhooks, setWebhooks] = useState<WebhookEventListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [eventTypeFilter, setEventTypeFilter] = useState<string>("all");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [search, setSearch] = useState("");
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [linkedRuns, setLinkedRuns] = useState<Record<string, ProcessingRunListItem[]>>({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [webhooksRes, countsRes, runsRes] = await Promise.allSettled([
          getWebhookEvents({ limit: 100, order: sortDir }),
          getWebhookEventStatusCounts(),
          getProcessingRuns({ limit: 100, order: "desc" }),
        ]);
        if (cancelled) return;
        if (webhooksRes.status === "fulfilled") {
          setWebhooks(webhooksRes.value.items);
          setTotal(webhooksRes.value.total);
        }
        if (countsRes.status === "fulfilled") {
          setStatusCounts(countsRes.value.status_counts ?? {});
        }
        if (runsRes.status === "fulfilled") {
          const runs = runsRes.value.items;
          const byWebhook: Record<string, ProcessingRunListItem[]> = {};
          runs.forEach((r) => {
            if (r.webhook_event_id) {
              if (!byWebhook[r.webhook_event_id]) byWebhook[r.webhook_event_id] = [];
              byWebhook[r.webhook_event_id].push(r);
            }
          });
          setLinkedRuns(byWebhook);
        }
        setLoading(false);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load webhooks");
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [sortDir]);

  const processedCount = (statusCounts["processed"] ?? 0) + (statusCounts["completed"] ?? 0);
  const pendingCount = (statusCounts["pending"] ?? 0) + (statusCounts["received"] ?? 0);
  const failedCount = (statusCounts["failed"] ?? 0) + (statusCounts["error"] ?? 0);
  const totalCount = Object.values(statusCounts).reduce((sum, c) => sum + (typeof c === "number" ? c : 0), 0) || total;

  const eventTypes = useMemo(() => {
    const types = new Set<string>();
    webhooks.forEach((w) => types.add(w.event_type));
    return Array.from(types).sort();
  }, [webhooks]);

  const filteredWebhooks = useMemo(() => {
    let list = webhooks;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (w) =>
          w.id.toLowerCase().includes(q) ||
          w.event_type.toLowerCase().includes(q) ||
          (w.zoom_event ?? "").toLowerCase().includes(q) ||
          w.status.toLowerCase().includes(q)
      );
    }
    if (statusFilter !== "all") {
      list = list.filter((w) => {
        const n = w.status.toLowerCase();
        if (statusFilter === "processed") return n === "processed" || n === "completed";
        if (statusFilter === "pending") return n === "pending" || n === "received";
        if (statusFilter === "failed") return n === "failed" || n === "error";
        return true;
      });
    }
    if (eventTypeFilter !== "all") {
      list = list.filter((w) => w.event_type === eventTypeFilter);
    }
    return list;
  }, [webhooks, search, statusFilter, eventTypeFilter]);

  const clientStatusCounts = useMemo(() => {
    const counts = { all: webhooks.length, processed: 0, pending: 0, failed: 0 };
    webhooks.forEach((w) => {
      const n = w.status.toLowerCase();
      if (n === "processed" || n === "completed") counts.processed++;
      else if (n === "pending" || n === "received") counts.pending++;
      else if (n === "failed" || n === "error") counts.failed++;
    });
    return counts;
  }, [webhooks]);

  const pagedWebhooks = useMemo(() => {
    return filteredWebhooks.slice(offset, offset + PAGE_SIZE);
  }, [filteredWebhooks, offset]);

  const totalPages = Math.ceil(filteredWebhooks.length / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const toggleSortDir = () => {
    setSortDir((d) => (d === "asc" ? "desc" : "asc"));
  };

  return (
    <AppShell>
      <div className="webhooks-page">
        <div className="page-header">
          <h1>Webhook Events</h1>
          <p className="page-header-subtitle">Monitor incoming Zoom webhook events and processing status</p>
        </div>

        {loading && <LoadingState message="Loading webhook events..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <div className="webhooks-summary">
              <div className="webhooks-summary-card">
                <div className="webhooks-summary-icon webhooks-summary-icon-primary">
                  <Webhook size={20} />
                </div>
                <div className="webhooks-summary-body">
                  <span className="webhooks-summary-value">{totalCount}</span>
                  <span className="webhooks-summary-label">Total Events</span>
                </div>
              </div>
              <div className="webhooks-summary-card">
                <div className="webhooks-summary-icon webhooks-summary-icon-success">
                  <CheckCircle2 size={20} />
                </div>
                <div className="webhooks-summary-body">
                  <span className="webhooks-summary-value">{processedCount}</span>
                  <span className="webhooks-summary-label">Processed</span>
                </div>
              </div>
              <div className="webhooks-summary-card">
                <div className="webhooks-summary-icon webhooks-summary-icon-muted">
                  <Clock size={20} />
                </div>
                <div className="webhooks-summary-body">
                  <span className="webhooks-summary-value">{pendingCount}</span>
                  <span className="webhooks-summary-label">Pending</span>
                </div>
              </div>
              <div className="webhooks-summary-card">
                <div className="webhooks-summary-icon webhooks-summary-icon-error">
                  <XCircle size={20} />
                </div>
                <div className="webhooks-summary-body">
                  <span className="webhooks-summary-value">{failedCount}</span>
                  <span className="webhooks-summary-label">Failed</span>
                </div>
              </div>
            </div>

            <section className="panel webhooks-panel">
              <div className="webhooks-toolbar">
                <div className="webhooks-search-wrap">
                  <Search size={16} className="webhooks-search-icon" />
                  <input
                    type="text"
                    className="webhooks-search-input"
                    placeholder="Search by event type, status, Zoom event..."
                    value={search}
                    onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
                  />
                </div>
                <div className="webhooks-filters">
                  <Filter size={14} className="webhooks-filter-icon" />
                  <select
                    className="filter-select"
                    value={statusFilter}
                    onChange={(e) => { setStatusFilter(e.target.value as StatusFilter); setOffset(0); }}
                  >
                    <option value="all">All Status ({clientStatusCounts.all})</option>
                    <option value="processed">Processed ({clientStatusCounts.processed})</option>
                    <option value="pending">Pending ({clientStatusCounts.pending})</option>
                    <option value="failed">Failed ({clientStatusCounts.failed})</option>
                  </select>
                  {eventTypes.length > 0 && (
                    <select
                      className="filter-select"
                      value={eventTypeFilter}
                      onChange={(e) => { setEventTypeFilter(e.target.value); setOffset(0); }}
                    >
                      <option value="all">All Types</option>
                      {eventTypes.map((t) => (
                        <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                      ))}
                    </select>
                  )}
                  <button className="webhooks-sort-btn" onClick={toggleSortDir} title={sortDir === "desc" ? "Newest first" : "Oldest first"}>
                    <ArrowUpDown size={14} />
                    {sortDir === "desc" ? "Newest" : "Oldest"}
                  </button>
                </div>
              </div>

              {pagedWebhooks.length > 0 ? (
                <div style={{ overflowX: "auto" }}>
                  <table className="meeting-table webhooks-table">
                    <thead>
                      <tr>
                        <th>Event ID</th>
                        <th>Event Type</th>
                        <th>Status</th>
                        <th>Zoom Event</th>
                        <th>
                          <button className="webhooks-th-btn" onClick={toggleSortDir}>
                            Received
                            <ArrowUpDown size={12} className="webhooks-sort-icon" />
                          </button>
                        </th>
                        <th>Processed At</th>
                        <th>Processing Runs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedWebhooks.map((wh) => {
                        const runs = linkedRuns[wh.id] ?? [];
                        return (
                          <tr key={wh.id}>
                            <td className="webhooks-cell-id">
                              <span className="webhooks-event-id">{wh.id.slice(0, 8)}</span>
                            </td>
                            <td>
                              <EventTypeBadge eventType={wh.event_type} />
                            </td>
                            <td>
                              <WebhookStatusBadge status={wh.status} />
                            </td>
                            <td className="webhooks-cell-zoom">
                              {wh.zoom_event ? (
                                <span className="webhooks-zoom-event" title={wh.zoom_event}>
                                  {wh.zoom_event.length > 30 ? wh.zoom_event.slice(0, 30) + "\u2026" : wh.zoom_event}
                                </span>
                              ) : (
                                <span className="webhooks-none">&mdash;</span>
                              )}
                            </td>
                            <td className="cell-date">{formatDateTime(wh.received_at)}</td>
                            <td className="cell-date">{wh.processed_at ? formatRelativeTime(wh.processed_at) : "\u2014"}</td>
                            <td>
                              {runs.length > 0 ? (
                                <div className="webhooks-linked-runs">
                                  {runs.slice(0, 2).map((r) => (
                                    <a
                                      key={r.id}
                                      href={`#/transcripts/${r.transcript_id}`}
                                      className="webhooks-linked-run"
                                    >
                                      <Activity size={12} />
                                      {r.id.slice(0, 8)}
                                      <RunMiniStatus status={r.status} />
                                    </a>
                                  ))}
                                  {runs.length > 2 && (
                                    <span className="webhooks-more-runs">+{runs.length - 2} more</span>
                                  )}
                                </div>
                              ) : (
                                <span className="webhooks-none">&mdash;</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title="No Webhook Events"
                  message={
                    search || statusFilter !== "all" || eventTypeFilter !== "all"
                      ? "No events match your filters. Try adjusting your search."
                      : "No webhook events received yet. Configure Zoom webhooks to start receiving events."
                  }
                />
              )}

              {totalPages > 1 && (
                <div className="pagination webhooks-pagination">
                  <button
                    className="pagination-btn"
                    disabled={currentPage <= 1}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    <ChevronLeft size={16} />
                    Previous
                  </button>
                  <span className="pagination-info">
                    Page {currentPage} of {totalPages} &middot; {filteredWebhooks.length} events
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

function RunMiniStatus({ status }: { status: string }) {
  const n = status.toLowerCase();
  let cls = "webhooks-run-dot-muted";
  if (n === "completed") cls = "webhooks-run-dot-success";
  else if (n === "failed") cls = "webhooks-run-dot-error";
  else if (n === "running" || n === "processing") cls = "webhooks-run-dot-warning";
  return <span className={`webhooks-run-dot ${cls}`} />;
}
