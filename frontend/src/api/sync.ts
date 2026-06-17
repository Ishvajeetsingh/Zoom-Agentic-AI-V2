import { apiGet, apiPost, apiPut } from "./client";
import type {
  SyncConfig,
  SyncConfigUpdateRequest,
  SyncHistoryListResponse,
  SyncNowResponse,
} from "../types/api";

export function getSyncConfig(accountId: string) {
  return apiGet<SyncConfig>(`/sync/config/${accountId}`);
}

export function updateSyncConfig(accountId: string, data: SyncConfigUpdateRequest) {
  return apiPut<SyncConfig>(`/sync/config/${accountId}`, data);
}

export function syncNow(accountId: string) {
  return apiPost<SyncNowResponse>(`/sync/now/${accountId}`);
}

export function syncAllEnabled() {
  return apiPost<SyncNowResponse>("/sync/all");
}

export function getSyncHistory(params?: {
  account_id?: string;
  offset?: number;
  limit?: number;
}) {
  return apiGet<SyncHistoryListResponse>("/sync/history", params as Record<string, string | number>);
}
