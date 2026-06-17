import { apiGet, apiPost, apiUpload } from "./client";
import type { TranscriptListItem, TranscriptDetail, PaginatedListResponse, TranscriptUploadResponse, PipelineResponse, OrchestrateResponse } from "../types/api";

export interface TranscriptListParams {
  offset?: number;
  limit?: number;
  status?: string;
  order_by?: string;
  order?: "asc" | "desc";
}

export function getTranscripts(params?: TranscriptListParams) {
  return apiGet<PaginatedListResponse<TranscriptListItem>>(
    "/transcripts",
    params as Record<string, string | number>
  );
}

export function getTranscript(transcriptId: string) {
  return apiGet<TranscriptDetail>(`/transcripts/${transcriptId}`);
}

export function uploadTranscript(file: File, meetingTopic?: string) {
  const formData = new FormData();
  formData.append("file", file);
  if (meetingTopic) formData.append("meeting_topic", meetingTopic);
  return apiUpload<TranscriptUploadResponse>("/transcripts/upload", formData);
}

export function runPipeline(transcriptId: string) {
  return apiPost<PipelineResponse>(`/transcripts/${transcriptId}/pipeline`);
}

export function orchestrateTranscript(transcriptId: string) {
  return apiPost<OrchestrateResponse>("/processing-runs", { transcript_id: transcriptId });
}
