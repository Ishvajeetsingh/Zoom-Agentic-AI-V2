import { apiGet } from "./client";
import type { PaginatedListResponse } from "../types/api";

export interface WebhookEventListItem {
  id: string;
  event_type: string;
  status: string;
  zoom_event: string | null;
  received_at: string;
  processed_at: string | null;
}

export interface WebhookEventListParams {
  event_type?: string;
  status?: string;
  offset?: number;
  limit?: number;
  order?: "asc" | "desc";
}

export function getWebhookEvents(params?: WebhookEventListParams) {
  return apiGet<PaginatedListResponse<WebhookEventListItem>>(
    "/webhooks/events",
    params as Record<string, string | number>
  );
}
