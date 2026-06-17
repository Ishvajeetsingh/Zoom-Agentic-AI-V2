import { apiGet, apiPost } from "./client";
import type { PaginatedListResponse } from "../types/api";

export interface ProcessingRunListItem {
  id: string;
  transcript_id: string;
  meeting_id: string | null;
  webhook_event_id: string | null;
  status: string;
  priority: number;
  retry_count: number;
  max_retries: number;
  warnings: string[];
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ProcessingRunListParams {
  transcript_id?: string;
  meeting_id?: string;
  status?: string;
  offset?: number;
  limit?: number;
  order?: "asc" | "desc";
}

export function getProcessingRuns(params?: ProcessingRunListParams) {
  return apiGet<PaginatedListResponse<ProcessingRunListItem>>(
    "/processing-runs",
    params as Record<string, string | number>
  );
}

export function retryProcessingRun(runId: string) {
  return apiPost<{ run_id: string; status: string }>(`/processing-runs/${runId}/retry`);
}

export function cancelProcessingRun(runId: string) {
  return apiPost<{ run_id: string; status: string }>(`/processing-runs/${runId}/cancel`);
}

