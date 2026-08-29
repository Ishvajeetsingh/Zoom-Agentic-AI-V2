import {
  apiGet,
  apiPost,
  apiUpload,
} from "./client";

import type {
  TranscriptListItem,
  TranscriptDetail,
  PaginatedListResponse,
  TranscriptUploadResponse,
  PipelineResponse,
  OrchestrateResponse,
} from "../types/api";

import { PUBLIC_DEMO_MODE } from "../config";


export interface TranscriptListParams {
  offset?: number;
  limit?: number;
  status?: string;
  order_by?: string;
  order?: "asc" | "desc";
}


/*
 * Normal/full application transcript listing.
 *
 * This remains intentionally protected by the backend
 * when PUBLIC_DEMO_MODE=true.
 */
export function getTranscripts(
  params?: TranscriptListParams
) {
  return apiGet<
    PaginatedListResponse<TranscriptListItem>
  >(
    "/transcripts",
    params as Record<
      string,
      string | number
    >
  );
}


/*
 * Normal/full transcript details.
 *
 * We do NOT redirect this to the public-demo API.
 * Historical/private transcript details remain protected.
 */
export function getTranscript(
  transcriptId: string
) {
  return apiGet<TranscriptDetail>(
    `/transcripts/${transcriptId}`
  );
}


/*
 * Upload a transcript.
 *
 * Normal application:
 *   /transcripts/upload
 *
 * Public portfolio:
 *   /public-demo/transcripts/upload
 */
export function uploadTranscript(
  file: File,
  meetingTopic?: string
) {
  const formData =
    new FormData();

  formData.append(
    "file",
    file
  );

  /*
   * The original endpoint supports meeting_topic.
   * The dedicated public-demo endpoint deliberately
   * ignores user-supplied meeting metadata.
   */
  if (
    meetingTopic &&
    !PUBLIC_DEMO_MODE
  ) {
    formData.append(
      "meeting_topic",
      meetingTopic
    );
  }


  const endpoint =
    PUBLIC_DEMO_MODE
      ? "/public-demo/transcripts/upload"
      : "/transcripts/upload";


  return apiUpload<
    TranscriptUploadResponse
  >(
    endpoint,
    formData
  );
}


/*
 * Run the existing processing pipeline.
 *
 * The backend public-demo endpoint still calls the
 * real ProcessingOrchestratorService. This is only
 * an API routing difference.
 */
export function runPipeline(
  transcriptId: string
) {
  const endpoint =
    PUBLIC_DEMO_MODE
      ? `/public-demo/transcripts/${transcriptId}/pipeline`
      : `/transcripts/${transcriptId}/pipeline`;


  return apiPost<
    PipelineResponse
  >(
    endpoint
  );
}


/*
 * Existing processing-run orchestration.
 *
 * Keep unchanged. This is used by the full application
 * and is not automatically exposed through public-demo.
 */
export function orchestrateTranscript(
  transcriptId: string
) {
  return apiPost<
    OrchestrateResponse
  >(
    "/processing-runs",
    {
      transcript_id:
        transcriptId,
    }
  );
}


/*
 * Generated questions for an uploaded public-demo transcript.
 *
 * This is deliberately separate from getTranscript().
 * We expose generated questions, not arbitrary transcript
 * content.
 */
export function getPublicDemoQuestions<
  T = unknown
>(
  transcriptId: string
) {
  return apiGet<T>(
    `/public-demo/transcripts/${transcriptId}/questions`
  );
}


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000/api/v1";


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


/*
 * Full-application export.
 *
 * This remains protected in public portfolio mode.
 */
export async function downloadDocx(
  transcriptId: string,
  filters?: DocxExportFilters
): Promise<void> {

  const response =
    await fetch(
      `${API_BASE_URL}/exports/transcripts/${transcriptId}/docx`,
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json",
        },

        body: JSON.stringify(
          filters ?? {}
        ),
      }
    );


  if (!response.ok) {
    let detail =
      await response
        .text()
        .catch(() => "");


    if (!detail) {
      if (
        response.status === 404
      ) {
        detail =
          "Transcript not found.";
      } else if (
        response.status === 400
      ) {
        detail =
          "DOCX file could not be generated for this transcript.";
      } else {
        detail =
          `Download failed (${response.status}).`;
      }
    }


    throw new Error(
      detail
    );
  }


  const blob =
    await response.blob();


  const contentDisposition =
    response.headers.get(
      "Content-Disposition"
    );


  let filename =
    `transcript_${transcriptId}.docx`;


  if (contentDisposition) {
    const match =
      contentDisposition.match(
        /filename\*?=(?:UTF-8'')?["']?([^;"'\n]+)/i
      );

    if (match) {
      filename =
        decodeURIComponent(
          match[1]
        );
    }
  }


  const url =
    URL.createObjectURL(
      blob
    );


  const anchor =
    document.createElement(
      "a"
    );

  anchor.href = url;
  anchor.download =
    filename;


  document.body.appendChild(
    anchor
  );

  anchor.click();

  document.body.removeChild(
    anchor
  );

  URL.revokeObjectURL(
    url
  );
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


/*
 * Full-application operation.
 *
 * This remains protected in public-demo mode.
 */
export function regenerateMcqs(
  transcriptId: string
) {
  return apiPost<
    RegenerateMcqsResponse
  >(
    `/transcripts/${transcriptId}/regenerate-mcqs`
  );
}