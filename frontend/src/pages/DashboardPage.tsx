import { useEffect, useState, useCallback } from "react";
import {
  Video,
  Activity,
  Webhook,
  BookOpen,
  Clock,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  Zap,
  Upload,
} from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { getMeetings } from "../api/meetings";
import { getProcessingRuns } from "../api/processingRuns";
import { getQueueMetrics, getWebhookEventStatusCounts } from "../api/metrics";
import { getWebhookEvents } from "../api/webhooks";
import { getTranscripts } from "../api/transcripts";
import type { TranscriptListItem } from "../types/api";
import type { ProcessingRunListItem } from "../api/processingRuns";
import type { QueueMetrics, WebhookStatusCounts } from "../api/metrics";
import type { WebhookEventListItem } from "../api/webhooks";

interface DashboardStats {
  totalMeetings: number;
  activeRuns: number;
  queuedRuns: number;
  failedRuns: number;
  completedRuns: number;
  completedWithWarningsRuns: number;
  webhookTotal: number;
  webhookPending: number;
  webhookProcessed: number;
  totalTranscripts: number;
  totalQuestions: number;
  queueMetrics: QueueMetrics | null;
  recentWebhooks: WebhookEventListItem[];
  recentTranscripts: TranscriptListItem[];
  recentRuns: ProcessingRunListItem[];
}

function StatCard({
  icon,
  label,
  value,
  variant,
  href,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  variant?: "default" | "success" | "warning" | "error" | "primary";
  href?: string;
}) {
  const variantClass = variant ? `metric-card-${variant}` : "";
  const content = (
    <div className={`dashboard-stat-card ${variantClass}`}>
      <div className="dashboard-stat-icon">{icon}</div>
      <div className="dashboard-stat-body">
        <span className="dashboard-stat-value">{value}</span>
        <span className="dashboard-stat-label">{label}</span>
      </div>
    </div>
  );

  if (href) {
    return (
      <a href={href} className="dashboard-stat-link">
        {content}
      </a>
    );
  }
  return content;
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return "—";
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

function RunStatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  if (normalized === "completed")
    return (
      <span className="status-badge status-completed">
        <span className="status-badge-dot" />
        Completed
      </span>
    );
  if (normalized === "completed_with_warnings")
    return (
      <span className="status-badge status-warning">
        <span className="status-badge-dot" />
        With Warnings
      </span>
    );
  if (normalized === "failed")
    return (
      <span className="status-badge status-failed">
        <span className="status-badge-dot" />
        Failed
      </span>
    );
  if (normalized === "running" || normalized === "processing")
    return (
      <span className="status-badge status-in-progress">
        <span className="status-badge-dot" />
        Running
      </span>
    );
  if (normalized === "queued" || normalized === "pending")
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

function WebhookStatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  if (normalized === "processed" || normalized === "completed")
    return <span className="status-badge status-completed">Processed</span>;
  if (normalized === "failed" || normalized === "error")
    return <span className="status-badge status-failed">Failed</span>;
  if (normalized === "pending" || normalized === "received")
    return <span className="status-badge status-pending">Pending</span>;
  return <span className="status-badge status-pending">{status}</span>;
}

export function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>({
    totalMeetings: 0,
    activeRuns: 0,
    queuedRuns: 0,
    failedRuns: 0,
    completedRuns: 0,
    completedWithWarningsRuns: 0,
    webhookTotal: 0,
    webhookPending: 0,
    webhookProcessed: 0,
    totalTranscripts: 0,
    totalQuestions: 0,
    queueMetrics: null,
    recentWebhooks: [],
    recentTranscripts: [],
    recentRuns: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    try {
      const [
        meetingsRes,
        runsRes,
        queueMetricsRes,
        webhookCountsRes,
        webhooksRes,
        transcriptsRes,
      ] = await Promise.allSettled([
        getMeetings({ limit: 1 }),
        getProcessingRuns({ limit: 50, order: "desc" }),
        getQueueMetrics(24),
        getWebhookEventStatusCounts(),
        getWebhookEvents({ limit: 5, order: "desc" }),
        getTranscripts({ limit: 5, order_by: "created_at", order: "desc" }),
      ]);

      const meetingsData = meetingsRes.status === "fulfilled" ? meetingsRes.value : null;
      const runsData = runsRes.status === "fulfilled" ? runsRes.value : null;
      const qmData = queueMetricsRes.status === "fulfilled" ? queueMetricsRes.value : null;
      const wcData = webhookCountsRes.status === "fulfilled" ? webhookCountsRes.value : null;
      const whData = webhooksRes.status === "fulfilled" ? webhooksRes.value : null;
      const tData = transcriptsRes.status === "fulfilled" ? transcriptsRes.value : null;

      const runs = runsData?.items ?? [];
      const activeRuns = runs.filter(
        (r) => r.status === "running" || r.status === "processing"
      ).length;
      const queuedRuns = runs.filter(
        (r) => r.status === "queued" || r.status === "pending"
      ).length;
      const failedRuns = qmData?.failed ?? 0;
      const completedRuns = qmData?.completed ?? 0;
      const completedWithWarningsRuns = runs.filter(
        (r) => r.status === "completed_with_warnings"
      ).length;

      const statusCounts = wcData?.status_counts ?? {};
      const webhookTotal = Object.values(statusCounts).reduce(
        (sum: number, c) => sum + (typeof c === "number" ? c : 0),
        0
      );
      const webhookPending = (statusCounts["pending"] ?? 0) + (statusCounts["received"] ?? 0);
      const webhookProcessed = (statusCounts["processed"] ?? 0) + (statusCounts["completed"] ?? 0);

      const recentTranscripts = tData?.items ?? [];
      const totalQuestions = (tData?.items ?? []).reduce(
        (sum, t) => sum + (t.question_count ?? 0),
        0
      );

      setStats({
        totalMeetings: meetingsData?.total ?? 0,
        activeRuns,
        queuedRuns,
        failedRuns,
        completedRuns,
        completedWithWarningsRuns,
        webhookTotal,
        webhookPending,
        webhookProcessed,
        totalTranscripts: tData?.total ?? recentTranscripts.length,
        totalQuestions,
        queueMetrics: qmData ?? null,
        recentWebhooks: whData?.items ?? [],
        recentTranscripts,
        recentRuns: runs.slice(0, 5),
      });
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [
          meetingsRes,
          runsRes,
          queueMetricsRes,
          webhookCountsRes,
          webhooksRes,
          transcriptsRes,
        ] = await Promise.allSettled([
          getMeetings({ limit: 1 }),
          getProcessingRuns({ limit: 50, order: "desc" }),
          getQueueMetrics(24),
          getWebhookEventStatusCounts(),
          getWebhookEvents({ limit: 5, order: "desc" }),
          getTranscripts({ limit: 5, order_by: "created_at", order: "desc" }),
        ]);

        if (cancelled) return;

        const meetingsData = meetingsRes.status === "fulfilled" ? meetingsRes.value : null;
        const runsData = runsRes.status === "fulfilled" ? runsRes.value : null;
        const qmData = queueMetricsRes.status === "fulfilled" ? queueMetricsRes.value : null;
        const wcData = webhookCountsRes.status === "fulfilled" ? webhookCountsRes.value : null;
        const whData = webhooksRes.status === "fulfilled" ? webhooksRes.value : null;
        const tData = transcriptsRes.status === "fulfilled" ? transcriptsRes.value : null;

        const runs = runsData?.items ?? [];
        const activeRuns = runs.filter(
          (r) => r.status === "running" || r.status === "processing"
        ).length;
        const queuedRuns = runs.filter(
          (r) => r.status === "queued" || r.status === "pending"
        ).length;
        const failedRuns = qmData?.failed ?? 0;
        const completedRunsVal = qmData?.completed ?? 0;
        const completedWithWarningsRuns = runs.filter(
          (r) => r.status === "completed_with_warnings"
        ).length;

        const statusCounts = wcData?.status_counts ?? {};
        const webhookTotal = Object.values(statusCounts).reduce(
          (sum: number, c) => sum + (typeof c === "number" ? c : 0),
          0
        );
        const webhookPending = (statusCounts["pending"] ?? 0) + (statusCounts["received"] ?? 0);
        const webhookProcessed = (statusCounts["processed"] ?? 0) + (statusCounts["completed"] ?? 0);

        const recentTranscripts = tData?.items ?? [];
        const totalQuestions = (tData?.items ?? []).reduce(
          (sum, t) => sum + (t.question_count ?? 0),
          0
        );

        setStats({
          totalMeetings: meetingsData?.total ?? 0,
          activeRuns,
          queuedRuns,
          failedRuns,
          completedRuns: completedRunsVal,
          completedWithWarningsRuns,
          webhookTotal,
          webhookPending,
          webhookProcessed,
          totalTranscripts: tData?.total ?? recentTranscripts.length,
          totalQuestions,
          queueMetrics: qmData ?? null,
          recentWebhooks: whData?.items ?? [],
          recentTranscripts,
          recentRuns: runs.slice(0, 5),
        });
        setLoading(false);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load dashboard");
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const successRate = stats.queueMetrics?.success_rate;
  const successRateDisplay =
    successRate != null ? `${(successRate * 100).toFixed(1)}%` : "—";

  return (
    <AppShell>
      <div className="dashboard-page">
        <div className="page-header">
          <h1>Dashboard</h1>
          <p className="page-header-subtitle">
            System overview and processing metrics
          </p>
        </div>

        {loading && <LoadingState message="Loading dashboard..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <div className="dashboard-stats-grid">
              <StatCard
                icon={<Video size={22} />}
                label="Total Meetings"
                value={stats.totalMeetings}
                variant="primary"
                href="#/meetings"
              />
              <StatCard
                icon={<Activity size={22} />}
                label="Active Runs"
                value={stats.activeRuns}
                variant={stats.activeRuns > 0 ? "warning" : "default"}
                href="#/queue"
              />
              <StatCard
                icon={<Clock size={22} />}
                label="Queued"
                value={stats.queuedRuns}
                href="#/queue"
              />
              <StatCard
                icon={<Webhook size={22} />}
                label="Webhook Events"
                value={stats.webhookTotal}
                href="#/webhooks"
              />
              <StatCard
                icon={<BookOpen size={22} />}
                label="Learning Outputs"
                value={stats.totalQuestions}
                href="#/learning"
              />
              <StatCard
                icon={<CheckCircle2 size={22} />}
                label="Success Rate"
                value={successRateDisplay}
                variant={successRate != null && successRate >= 0.9 ? "success" : "default"}
                href="#/queue"
              />
            </div>

            <div className="dashboard-grid-2col">
              <section className="panel dashboard-panel">
                <div className="panel-header">
                  <h2 className="panel-title">Queue Health</h2>
                  <a href="#/queue" className="link-view">
                    View all <ArrowRight size={14} />
                  </a>
                </div>
                <div className="dashboard-queue-metrics">
                  <div className="dashboard-mini-stat">
                    <span className="dashboard-mini-stat-dot dot-success" />
                    <span className="dashboard-mini-stat-value">{stats.completedRuns}</span>
                    <span className="dashboard-mini-stat-label">Completed</span>
                  </div>
                  <div className="dashboard-mini-stat">
                    <span className="dashboard-mini-stat-dot dot-warning" />
                    <span className="dashboard-mini-stat-value">{stats.completedWithWarningsRuns}</span>
                    <span className="dashboard-mini-stat-label">With Warnings</span>
                  </div>
                  <div className="dashboard-mini-stat">
                    <span className="dashboard-mini-stat-dot dot-warning" />
                    <span className="dashboard-mini-stat-value">{stats.activeRuns}</span>
                    <span className="dashboard-mini-stat-label">Running</span>
                  </div>
                  <div className="dashboard-mini-stat">
                    <span className="dashboard-mini-stat-dot dot-muted" />
                    <span className="dashboard-mini-stat-value">{stats.queuedRuns}</span>
                    <span className="dashboard-mini-stat-label">Queued</span>
                  </div>
                  <div className="dashboard-mini-stat">
                    <span className="dashboard-mini-stat-dot dot-error" />
                    <span className="dashboard-mini-stat-value">{stats.failedRuns}</span>
                    <span className="dashboard-mini-stat-label">Failed</span>
                  </div>
                </div>
                {stats.recentRuns.length > 0 && (
                  <div className="dashboard-recent-list">
                    {stats.recentRuns.map((run) => (
                      <div key={run.id} className="dashboard-recent-item">
                        <div className="dashboard-recent-item-left">
                          <RunStatusBadge status={run.status} />
                          <span className="dashboard-recent-item-id">
                            {run.id.slice(0, 8)}
                          </span>
                        </div>
                        <span className="dashboard-recent-item-time">
                          {formatRelativeTime(run.created_at)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="panel dashboard-panel">
                <div className="panel-header">
                  <h2 className="panel-title">Webhook Events</h2>
                  <a href="#/webhooks" className="link-view">
                    View all <ArrowRight size={14} />
                  </a>
                </div>
                <div className="dashboard-queue-metrics">
                  <div className="dashboard-mini-stat">
                    <span className="dashboard-mini-stat-dot dot-success" />
                    <span className="dashboard-mini-stat-value">{stats.webhookProcessed}</span>
                    <span className="dashboard-mini-stat-label">Processed</span>
                  </div>
                  <div className="dashboard-mini-stat">
                    <span className="dashboard-mini-stat-dot dot-warning" />
                    <span className="dashboard-mini-stat-value">{stats.webhookPending}</span>
                    <span className="dashboard-mini-stat-label">Pending</span>
                  </div>
                  <div className="dashboard-mini-stat">
                    <span className="dashboard-mini-stat-dot dot-muted" />
                    <span className="dashboard-mini-stat-value">{stats.webhookTotal}</span>
                    <span className="dashboard-mini-stat-label">Total</span>
                  </div>
                </div>
                {stats.recentWebhooks.length > 0 && (
                  <div className="dashboard-recent-list">
                    {stats.recentWebhooks.map((wh) => (
                      <div key={wh.id} className="dashboard-recent-item">
                        <div className="dashboard-recent-item-left">
                          <WebhookStatusBadge status={wh.status} />
                          <span className="dashboard-recent-item-id">
                            {wh.event_type}
                          </span>
                        </div>
                        <span className="dashboard-recent-item-time">
                          {formatRelativeTime(wh.received_at)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {stats.recentWebhooks.length === 0 && (
                  <div className="dashboard-empty-section">
                    <Webhook size={24} />
                    <span>No webhook events yet</span>
                  </div>
                )}
              </section>
            </div>

            <section className="panel dashboard-panel">
              <div className="panel-header">
                <h2 className="panel-title">Recent Activity</h2>
              </div>
              {stats.recentTranscripts.length > 0 ? (
                <table className="meeting-table">
                  <thead>
                    <tr>
                      <th>Filename</th>
                      <th>Status</th>
                      <th>Questions</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.recentTranscripts.map((t) => (
                      <tr key={t.id}>
                        <td className="cell-filename">
                          <a
                            href={`#/transcripts/${t.id}`}
                            className="link-view"
                            style={{ textDecoration: "none" }}
                          >
                            {t.transcript_filename || t.id.slice(0, 8)}
                          </a>
                        </td>
                        <td>
                          <span
                            className={`status-badge ${
                              t.status === "completed"
                                ? "status-completed"
                                : t.status === "completed_with_warnings"
                                ? "status-warning"
                                : t.status.endsWith("_failed") || t.status === "failed"
                                ? "status-failed"
                                : t.status === "generating"
                                ? "status-in-progress"
                                : "status-pending"
                            }`}
                          >
                            <span className="status-badge-dot" />
                            {t.status.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td className="cell-number">{t.question_count ?? 0}</td>
                        <td className="cell-date">{formatRelativeTime(t.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="dashboard-empty-section">
                  <Activity size={24} />
                  <span>No activity recorded yet</span>
                </div>
              )}
            </section>

            <div className="quick-action-grid">
              <a href="#/process-meeting" className="quick-action-card">
                <div
                  className="quick-action-card-icon"
                  style={{
                    background: "var(--c-primary-light)",
                    color: "var(--c-primary)",
                  }}
                >
                  <Zap size={22} />
                </div>
                <h3 className="quick-action-card-title">Process Meeting</h3>
                <p className="quick-action-card-desc">
                  Ingest a Zoom recording and run the full processing pipeline
                </p>
              </a>
              <a href="#/upload-transcript" className="quick-action-card">
                <div
                  className="quick-action-card-icon"
                  style={{
                    background: "var(--c-success-light)",
                    color: "var(--c-success)",
                  }}
                >
                  <Upload size={22} />
                </div>
                <h3 className="quick-action-card-title">Upload Transcript</h3>
                <p className="quick-action-card-desc">
                  Upload a VTT, JSON, or TXT transcript file and generate questions
                </p>
              </a>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
