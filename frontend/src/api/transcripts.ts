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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export interface McqFilters {
  difficulty?: string;
  category?: string;
  bloom?: string;
  top?: number;
}

export interface FlashcardFilters {
  category?: string;
  difficulty?: string;
  top?: number;
}

export interface ShortQuestionFilters {
  category?: string;
  difficulty?: string;
  bloom?: string;
  top?: number;
}

export interface DocxExportFilters {
  mcq?: McqFilters;
  flashcard?: FlashcardFilters;
  short_question?: ShortQuestionFilters;
}

export async function downloadDocx(transcriptId: string, filters?: DocxExportFilters): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/exports/transcripts/${transcriptId}/docx`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filters ?? {}),
  });
  if (!response.ok) {
    let detail = await response.text().catch(() => "");
    if (!detail) {
      if (response.status === 404) detail = "Transcript not found.";
      else if (response.status === 400) detail = "DOCX file could not be generated for this transcript.";
      else detail = `Download failed (${response.status}).`;
    }
    throw new Error(detail);
  }
  const blob = await response.blob();
  const contentDisposition = response.headers.get("Content-Disposition");
  let filename = `transcript_${transcriptId}.docx`;
  if (contentDisposition) {
    const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?["']?([^;"'\n]+)/i);
    if (match) filename = decodeURIComponent(match[1]);
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export interface RegenerateMcqsResponse {
  transcript_id: string;
  meeting_id: string;
  previous_count: number;
  new_count: number;
  chunks_processed: number;
  duplicates_removed: number;
  classified: number;
  ranked: number;
  model_used: string;
  aborted: boolean;
  abort_reason: string | null;
}

export function regenerateMcqs(transcriptId: string) {
  return apiPost<RegenerateMcqsResponse>(`/transcripts/${transcriptId}/regenerate-mcqs`);
}
