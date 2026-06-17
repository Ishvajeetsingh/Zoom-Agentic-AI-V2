import { apiGet } from "./client";

export interface QueueMetrics {
  total_runs: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
  avg_duration_seconds: number | null;
  success_rate: number | null;
}

export interface WebhookStatusCounts {
  status_counts: Record<string, number>;
}

export function getMetrics() {
  return apiGet<{ items: unknown[] }>("/metrics");
}

export function getQueueMetrics(hours?: number) {
  return apiGet<QueueMetrics>("/processing-runs/metrics", hours ? { hours } : undefined);
}

export function getWebhookEventStatusCounts() {
  return apiGet<WebhookStatusCounts>("/webhooks/events/status-counts");
}

