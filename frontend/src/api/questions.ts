import { apiGet, apiPost } from "./client";
import type { Question, PaginatedListResponse } from "../types/api";

export interface QuestionFilters {
  offset?: number;
  limit?: number;
  difficulty?: string;
  question_type?: string;
  category?: string;
  bloom?: string;
  top?: number;
  order?: "asc" | "desc";
}

export function getTranscriptQuestions(
  transcriptId: string,
  filters?: QuestionFilters
) {
  return apiGet<PaginatedListResponse<Question>>(
    `/transcripts/${transcriptId}/questions`,
    filters as Record<string, string | number>
  );
}

export function getPublicTranscriptQuestions(
  transcriptId: string
) {
  return apiGet<PaginatedListResponse<Question>>(
    `/public-demo/transcripts/${transcriptId}/questions`
  );
}

export function classifyTranscript(transcriptId: string) {
  return apiPost<{ transcript_id: string; questions_classified: number; learning_outputs_classified: number }>(
    `/transcripts/${transcriptId}/classify`
  );
}
