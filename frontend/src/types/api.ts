export type QuestionType = "mcq" | "short_answer" | "true_false" | "fill_blank";
export type Difficulty = "easy" | "medium" | "hard";
export type TranscriptStatus =
  | "metadata_received"
  | "download_started"
  | "downloaded"
  | "parsing_started"
  | "parsed"
  | "parsing_failed"
  | "cleaning_started"
  | "cleaned"
  | "cleaning_failed"
  | "chunking_started"
  | "chunked"
  | "chunking_failed"
  | "assessing"
  | "generating"
  | "generating_learning_outputs"
  | "learning_generation_failed"
  | "synthesizing"
  | "synthesis_failed"
  | "completed"
  | "completed_with_warnings"
  | "generation_failed"
  | "failed";

export interface PaginatedListResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface MeetingListItem {
  id: string;
  source: string;
  zoom_meeting_id: string | null;
  zoom_uuid: string | null;
  topic: string | null;
  start_time: string | null;
  timezone: string | null;
  duration_minutes: number | null;
  participant_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface MeetingDetail {
  id: string;
  source: string;
  zoom_meeting_id: string | null;
  zoom_uuid: string | null;
  account_id: string | null;
  host_id: string | null;
  host_email: string | null;
  topic: string | null;
  start_time: string | null;
  timezone: string | null;
  duration_minutes: number | null;
  participant_count: number | null;
  transcript_count: number;
  question_count: number;
  created_at: string;
  updated_at: string;
}

export interface TranscriptListItem {
  id: string;
  meeting_id: string;
  source_format: string | null;
  status: TranscriptStatus;
  transcript_filename: string | null;
  file_type: string | null;
  file_size_bytes: number | null;
  segment_count: number | null;
  chunk_count: number | null;
  question_count: number | null;
  warnings: string[];
  created_at: string;
  updated_at: string;
}

export interface TranscriptDetail {
  id: string;
  meeting_id: string;
  source_format: string | null;
  status: TranscriptStatus;
  transcript_filename: string | null;
  raw_file_path: string | null;
  processed_file_path: string | null;
  zoom_file_id: string | null;
  zoom_recording_type: string | null;
  file_type: string | null;
  file_extension: string | null;
  file_size_bytes: number | null;
  recording_start: string | null;
  recording_end: string | null;
  language: string | null;
  segment_count: number;
  word_count: number | null;
  cleaned_segment_count: number | null;
  cleaned_word_count: number | null;
  chunk_count: number;
  question_count: number;
  generation_model: string | null;
  checksum_sha256: string | null;
  warnings: string[];
  created_at: string;
  updated_at: string;
}

export interface Question {
  id: string;
  transcript_id: string;
  meeting_id: string;
  chunk_id: string | null;
  chunk_index: number | null;
  question_text: string;
  question_type: QuestionType;
  options: string[];
  correct_answer: string;
  explanation: string;
  difficulty: Difficulty;
  is_valid: boolean;
  is_duplicate: boolean;
  duplicate_of: string | null;
  created_at: string;
}

export interface QuestionListResponse {
  items: Question[];
  total: number;
  offset: number;
  limit: number;
}

export interface ZoomIngestResponse {
  meeting_id: string;
  transcript_id: string | null;
  recording_found: boolean;
  zoom_meeting_id: string | null;
  zoom_uuid: string;
  topic: string | null;
}

export interface TranscriptUploadResponse {
  transcript_id: string;
  meeting_id: string;
  transcript_filename: string;
  file_size_bytes: number;
  source_format: string;
  status: string;
}

export interface DiscoveredMeeting {
  meeting_id: string;
  uuid: string;
  topic: string | null;
  start_time: string | null;
  duration_minutes: number | null;
  participant_count: number | null;
  has_transcript: boolean;
  recording_count: number;
}

export interface DiscoverMeetingsResponse {
  meetings: DiscoveredMeeting[];
  total: number;
}

export interface DiscoverTranscriptsResponse {
  meeting_id: string;
  transcripts_found: boolean;
  transcript_ids: string[];
  recording_files: { id: string; file_type: string; file_extension: string }[];
}

export interface OrchestrateResponse {
  run_id: string;
  transcript_id: string;
  meeting_id: string | null;
  status: string;
  steps_completed: number;
  total_steps: number;
  questions_generated: number;
  model_used: string | null;
  error_message: string | null;
  total_duration_seconds: number | null;
}

export interface PipelineStepResult {
  step: string;
  status: string;
  [key: string]: unknown;
}

export interface PipelineResponse {
  transcript_id: string;
  status: string;
  steps: PipelineStepResult[];
  errors: string[];
}

export interface ZoomAccount {
  id: string;
  account_name: string;
  zoom_account_id: string;
  client_id: string;
  enabled: boolean;
  is_default: boolean;
  token_url: string;
  api_base_url: string;
  notes: string | null;
  last_sync_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ZoomAccountListResponse {
  items: ZoomAccount[];
  total: number;
}

export interface ZoomAccountCreateRequest {
  account_name: string;
  zoom_account_id: string;
  client_id: string;
  client_secret: string;
  enabled?: boolean;
  is_default?: boolean;
  token_url?: string;
  api_base_url?: string;
  notes?: string;
}

export interface ZoomAccountUpdateRequest {
  account_name?: string;
  zoom_account_id?: string;
  client_id?: string;
  client_secret?: string;
  enabled?: boolean;
  is_default?: boolean;
  token_url?: string;
  api_base_url?: string;
  notes?: string;
}

export interface SyncConfig {
  id: string;
  zoom_account_id: string;
  auto_sync_enabled: boolean;
  sync_interval_minutes: number;
  lookback_days: number;
  auto_process: boolean;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface SyncConfigUpdateRequest {
  auto_sync_enabled?: boolean;
  sync_interval_minutes?: number;
  lookback_days?: number;
  auto_process?: boolean;
}

export interface SyncHistoryEntry {
  id: string;
  zoom_account_id: string;
  sync_type: string;
  status: string;
  meetings_discovered: number;
  transcripts_discovered: number;
  transcripts_queued: number;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
}

export interface SyncHistoryListResponse {
  items: SyncHistoryEntry[];
  total: number;
}

export interface SyncNowResponse {
  success: boolean;
  message: string;
  sync_history_id: string | null;
}


