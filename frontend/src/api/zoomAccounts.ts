import { apiGet, apiPost, apiPut, apiDelete } from "./client";
import type {
  ZoomAccount,
  ZoomAccountListResponse,
  ZoomAccountCreateRequest,
  ZoomAccountUpdateRequest,
} from "../types/api";

export function getZoomAccounts(offset = 0, limit = 100) {
  return apiGet<ZoomAccountListResponse>("/zoom-accounts", { offset, limit });
}

export function getEnabledZoomAccounts() {
  return apiGet<ZoomAccountListResponse>("/zoom-accounts/enabled");
}

export function getZoomAccount(accountId: string) {
  return apiGet<ZoomAccount>(`/zoom-accounts/${accountId}`);
}

export function createZoomAccount(data: ZoomAccountCreateRequest) {
  return apiPost<ZoomAccount>("/zoom-accounts", data);
}

export function updateZoomAccount(accountId: string, data: ZoomAccountUpdateRequest) {
  return apiPut<ZoomAccount>(`/zoom-accounts/${accountId}`, data);
}

export function deleteZoomAccount(accountId: string) {
  return apiDelete(`/zoom-accounts/${accountId}`);
}

export function setDefaultZoomAccount(accountId: string) {
  return apiPost<ZoomAccount>(`/zoom-accounts/${accountId}/set-default`);
}
