import { useEffect, useState, useCallback, useMemo } from "react";
import {
  Search,
  Filter,
  Video,
  Clock,
  Users,
  FileText,
  Activity,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";
import { getMeetings } from "../api/meetings";
import { getTranscripts } from "../api/transcripts";
import { getProcessingRuns } from "../api/processingRuns";
import type { MeetingListItem, TranscriptListItem } from "../types/api";
import type { ProcessingRunListItem } from "../api/processingRuns";

const PAGE_SIZE = 20;

type MeetingSource = "all" | "zoom" | "upload";
type SortField = "start_time" | "topic" | "created_at";
type SortDir = "asc" | "desc";

interface MeetingEnrichment {
  transcriptStatus: string | null;
  processingStatus: string | null;
  transcriptCount: number;
  questionCount: number;
}

function MeetingStatusBadge({ source }: { source: string }) {
  if (source === "zoom")
    return (
      <span className="status-badge status-completed">
        <span className="status-badge-dot" />
        Zoom
      </span>
    );
  if (source === "upload" || source === "manual")
    return (
      <span className="status-badge status-pending">
        <span className="status-badge-dot" />
        Upload
      </span>
    );
  return (
    <span className="status-badge status-pending">
      <span className="status-badge-dot" />
      {source}
    </span>
  );
}

function TranscriptStatusBadge({ status }: { status: string | null }) {
  if (!status)
    return (
      <span className="meetings-monitor-none">&mdash;</span>
    );
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
  if (n.endsWith("_failed") || n === "failed")
    return (
      <span className="status-badge status-failed">
        <span className="status-badge-dot" />
        Failed
      </span>
    );
  if (n === "generating" || n.includes("started"))
    return (
      <span className="status-badge status-in-progress">
        <span className="status-badge-dot" />
        Processing
      </span>
    );
  return (
    <span className="status-badge status-pending">
      <span className="status-badge-dot" />
      {status.replace(/_/g, " ")}
    </span>
  );
}

function ProcessingStatusBadge({ status }: { status: string | null }) {
  if (!status)
    return (
      <span className="meetings-monitor-none">&mdash;</span>
    );
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
  return (
    <span className="status-badge status-pending">
      <span className="status-badge-dot" />
      {status}
    </span>
  );
}

function formatRelativeDate(iso: string | null): string {
  if (!iso) return "\u2014";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString();
}

export function MeetingsPage() {
  const [meetings, setMeetings] = useState<MeetingListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<MeetingSource>("all");
  const [sortField, setSortField] = useState<SortField>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const [enrichment, setEnrichment] = useState<Record<string, MeetingEnrichment>>({});
  const [enrichmentLoading, setEnrichmentLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const orderBy = sortField === "start_time" ? "start_time" : sortField;
      const res = await getMeetings({
        offset,
        limit: PAGE_SIZE,
        order_by: orderBy,
        order: sortDir,
      });
      setMeetings(res.items);
      setTotal(res.total);
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load meetings");
      setLoading(false);
    }
  }, [offset, sortField, sortDir]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const orderBy = sortField === "start_time" ? "start_time" : sortField;
        const res = await getMeetings({
          offset,
          limit: PAGE_SIZE,
          order_by: orderBy,
          order: sortDir,
        });
        if (!cancelled) {
          setMeetings(res.items);
          setTotal(res.total);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load meetings");
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [offset, sortField, sortDir]);

  useEffect(() => {
    if (meetings.length === 0) {
      setEnrichment({});
      return;
    }

    let cancelled = false;
    setEnrichmentLoading(true);

    (async () => {
      try {
        const meetingIds = meetings.map((m) => m.id);
        const enrichMap: Record<string, MeetingEnrichment> = {};

        meetingIds.forEach((id) => {
          enrichMap[id] = {
            transcriptStatus: null,
            processingStatus: null,
            transcriptCount: 0,
            questionCount: 0,
          };
        });

        const [transRes, runsRes] = await Promise.allSettled([
          getTranscripts({ limit: 100, order_by: "created_at", order: "desc" }),
          getProcessingRuns({ limit: 100, order: "desc" }),
        ]);

        if (cancelled) return;

        if (transRes.status === "fulfilled") {
          const transcripts = transRes.value.items as TranscriptListItem[];
          const byMeeting: Record<string, TranscriptListItem[]> = {};
          transcripts.forEach((t) => {
            if (!byMeeting[t.meeting_id]) byMeeting[t.meeting_id] = [];
            byMeeting[t.meeting_id].push(t);
          });
          meetingIds.forEach((id) => {
            const mt = byMeeting[id] ?? [];
            if (mt.length > 0) {
              enrichMap[id] = {
                ...enrichMap[id],
                transcriptCount: mt.length,
                questionCount: mt.reduce((sum, t) => sum + (t.question_count ?? 0), 0),
                transcriptStatus: mt[0].status,
              };
            }
          });
        }

        if (runsRes.status === "fulfilled") {
          const runs = runsRes.value.items as ProcessingRunListItem[];
          const byMeeting: Record<string, ProcessingRunListItem[]> = {};
          runs.forEach((r) => {
            const mid = r.meeting_id;
            if (mid && !byMeeting[mid]) byMeeting[mid] = [];
            if (mid) byMeeting[mid].push(r);
          });
          meetingIds.forEach((id) => {
            const mr = byMeeting[id] ?? [];
            if (mr.length > 0) {
              const latest = mr[0];
              enrichMap[id] = {
                ...enrichMap[id],
                processingStatus: latest.status,
              };
            }
          });
        }

        if (!cancelled) {
          setEnrichment(enrichMap);
          setEnrichmentLoading(false);
        }
      } catch {
        if (!cancelled) setEnrichmentLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [meetings]);

  const filteredMeetings = useMemo(() => {
    let list = meetings;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (m) =>
          (m.topic ?? "").toLowerCase().includes(q) ||
          (m.zoom_meeting_id ?? "").toLowerCase().includes(q) ||
          m.id.toLowerCase().includes(q)
      );
    }
    if (sourceFilter !== "all") {
      list = list.filter((m) => m.source === sourceFilter);
    }
    return list;
  }, [meetings, search, sourceFilter]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const sourceCounts = useMemo(() => {
    const counts = { all: meetings.length, zoom: 0, upload: 0 };
    meetings.forEach((m) => {
      if (m.source === "zoom") counts.zoom++;
      else counts.upload++;
    });
    return counts;
  }, [meetings]);

  const summaryStats = useMemo(() => {
    let withTranscripts = 0;
    let withQuestions = 0;
    let processingActive = 0;
    meetings.forEach((m) => {
      const e = enrichment[m.id];
      if (e) {
        if (e.transcriptCount > 0) withTranscripts++;
        if (e.questionCount > 0) withQuestions++;
        if (e.processingStatus === "running" || e.processingStatus === "processing") processingActive++;
      }
    });
    return { withTranscripts, withQuestions, processingActive };
  }, [meetings, enrichment]);

  return (
    <AppShell>
      <div className="meetings-monitor-page">
        <div className="page-header">
          <h1>Meetings Monitor</h1>
          <p className="page-header-subtitle">
            Track meeting ingestion, transcripts, and processing pipeline status
          </p>
        </div>

        {loading && <LoadingState message="Loading meetings..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <div className="meetings-monitor-summary">
              <div className="meetings-monitor-summary-card">
                <div className="meetings-monitor-summary-icon meetings-monitor-summary-icon-primary">
                  <Video size={20} />
                </div>
                <div className="meetings-monitor-summary-body">
                  <span className="meetings-monitor-summary-value">{total}</span>
                  <span className="meetings-monitor-summary-label">Total Meetings</span>
                </div>
              </div>
              <div className="meetings-monitor-summary-card">
                <div className="meetings-monitor-summary-icon meetings-monitor-summary-icon-success">
                  <FileText size={20} />
                </div>
                <div className="meetings-monitor-summary-body">
                  <span className="meetings-monitor-summary-value">{summaryStats.withTranscripts}</span>
                  <span className="meetings-monitor-summary-label">Has Transcripts</span>
                </div>
              </div>
              <div className="meetings-monitor-summary-card">
                <div className="meetings-monitor-summary-icon meetings-monitor-summary-icon-warning">
                  <Activity size={20} />
                </div>
                <div className="meetings-monitor-summary-body">
                  <span className="meetings-monitor-summary-value">
                    {enrichmentLoading ? "\u2026" : summaryStats.processingActive}
                  </span>
                  <span className="meetings-monitor-summary-label">Processing</span>
                </div>
              </div>
              <div className="meetings-monitor-summary-card">
                <div className="meetings-monitor-summary-icon meetings-monitor-summary-icon-primary">
                  <Users size={20} />
                </div>
                <div className="meetings-monitor-summary-body">
                  <span className="meetings-monitor-summary-value">{summaryStats.withQuestions}</span>
                  <span className="meetings-monitor-summary-label">Has Questions</span>
                </div>
              </div>
            </div>

            <section className="panel meetings-monitor-panel">
              <div className="meetings-monitor-toolbar">
                <div className="meetings-monitor-search-wrap">
                  <Search size={16} className="meetings-monitor-search-icon" />
                  <input
                    type="text"
                    className="meetings-monitor-search-input"
                    placeholder="Search by topic, meeting ID..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <div className="meetings-monitor-filters">
                  <Filter size={14} className="meetings-monitor-filter-icon" />
                  <select
                    className="filter-select"
                    value={sourceFilter}
                    onChange={(e) => setSourceFilter(e.target.value as MeetingSource)}
                  >
                    <option value="all">All Sources ({sourceCounts.all})</option>
                    <option value="zoom">Zoom ({sourceCounts.zoom})</option>
                    <option value="upload">Upload ({sourceCounts.upload})</option>
                  </select>
                </div>
              </div>

              {filteredMeetings.length > 0 ? (
                <div style={{ overflowX: "auto" }}>
                  <table className="meeting-table meetings-monitor-table">
                    <thead>
                      <tr>
                        <th className="meetings-monitor-col-topic">
                          <button
                            className="meetings-monitor-th-btn"
                            onClick={() => toggleSort("topic")}
                          >
                            Topic
                            {sortField === "topic" && (
                              <ArrowUpDown size={12} className="meetings-monitor-sort-icon" />
                            )}
                          </button>
                        </th>
                        <th>Source</th>
                        <th>
                          <button
                            className="meetings-monitor-th-btn"
                            onClick={() => toggleSort("start_time")}
                          >
                            Start Time
                            {sortField === "start_time" && (
                              <ArrowUpDown size={12} className="meetings-monitor-sort-icon" />
                            )}
                          </button>
                        </th>
                        <th>Duration</th>
                        <th>Transcript Status</th>
                        <th>Processing</th>
                        <th>Transcripts</th>
                        <th>
                          <button
                            className="meetings-monitor-th-btn"
                            onClick={() => toggleSort("created_at")}
                          >
                            Created
                            {sortField === "created_at" && (
                              <ArrowUpDown size={12} className="meetings-monitor-sort-icon" />
                            )}
                          </button>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredMeetings.map((m) => {
                        const e = enrichment[m.id];
                        return (
                          <tr key={m.id}>
                            <td className="cell-filename meetings-monitor-cell-topic">
                              <a
                                href={`#/meetings/${m.id}`}
                                className="meetings-monitor-topic-link"
                              >
                                {m.topic ?? "Untitled Meeting"}
                              </a>
                              {m.zoom_meeting_id && (
                                <span className="meetings-monitor-zoom-id">
                                  {m.zoom_meeting_id}
                                </span>
                              )}
                            </td>
                            <td>
                              <MeetingStatusBadge source={m.source} />
                            </td>
                            <td className="cell-date">
                              {m.start_time
                                ? new Date(m.start_time).toLocaleDateString(undefined, {
                                    month: "short",
                                    day: "numeric",
                                    year: "numeric",
                                  })
                                : "\u2014"}
                            </td>
                            <td className="cell-number">
                              {m.duration_minutes != null
                                ? `${m.duration_minutes} min`
                                : "\u2014"}
                            </td>
                            <td>
                              <TranscriptStatusBadge
                                status={e?.transcriptStatus ?? null}
                              />
                            </td>
                            <td>
                              <ProcessingStatusBadge
                                status={e?.processingStatus ?? null}
                              />
                            </td>
                            <td className="cell-number">
                              {e?.transcriptCount ?? 0}
                            </td>
                            <td className="cell-date">
                              {formatRelativeDate(m.created_at)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title="No Meetings"
                  message={
                    search || sourceFilter !== "all"
                      ? "No meetings match your filters. Try adjusting your search."
                      : "No meetings found. Process a Zoom recording to get started."
                  }
                />
              )}

              {totalPages > 1 && (
                <div className="pagination meetings-monitor-pagination">
                  <button
                    className="pagination-btn"
                    disabled={currentPage <= 1}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    <ChevronLeft size={16} />
                    Previous
                  </button>
                  <span className="pagination-info">
                    Page {currentPage} of {totalPages} &middot; {total} meetings
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
