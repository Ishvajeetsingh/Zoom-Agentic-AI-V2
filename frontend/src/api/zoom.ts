import { apiPost } from "./client";
import type { ZoomIngestResponse, DiscoverMeetingsResponse, DiscoverTranscriptsResponse } from "../types/api";

export interface ZoomIngestRequest {
  meeting_uuid: string;
}

export function ingestZoomMeeting(request: ZoomIngestRequest) {
  return apiPost<ZoomIngestResponse>("/zoom/ingest", request);
}

export interface DiscoverMeetingsRequest {
  from?: string;
  to?: string;
  page_size?: number;
  next_page_token?: string;
}

export function discoverMeetings(request?: DiscoverMeetingsRequest) {
  return apiPost<DiscoverMeetingsResponse>("/zoom/discover-meetings", request);
}

export function discoverTranscripts(meetingId: string) {
  return apiPost<DiscoverTranscriptsResponse>(`/zoom/discover-transcripts/${meetingId}`);
}

export function orchestrateZoomMeeting(meetingUuid: string) {
  return apiPost<OrchestrateZoomResponse>("/zoom/orchestrate", { meeting_uuid: meetingUuid });
}

export interface OrchestrateZoomResponse {
  run_id: string;
  meeting_id: string;
  transcript_id: string | null;
  status: string;
  message: string;
}
