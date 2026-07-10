import { apiGet } from "./client";
import type { MeetingListItem, MeetingDetail } from "../types/api";

export type { MeetingListItem, MeetingDetail };

export interface MeetingListParams {
  offset?: number;
  limit?: number;
  order_by?: string;
  order?: "asc" | "desc";
}

export function getMeetings(params?: MeetingListParams) {
  return apiGet<{ items: MeetingListItem[]; total: number; offset: number; limit: number }>("/meetings", params as Record<string, string | number>);
}

export function getMeeting(meetingId: string) {
  return apiGet<MeetingDetail>(`/meetings/${meetingId}`);
}

export function listMeetings(params?: MeetingListParams) {
  return apiGet<{ items: MeetingListItem[]; total: number; offset: number; limit: number }>("/meetings", params as Record<string, string | number>);
}
