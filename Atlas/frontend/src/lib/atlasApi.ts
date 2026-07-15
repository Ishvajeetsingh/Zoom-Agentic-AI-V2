const API_BASE = (import.meta.env.VITE_ATLAS_API_BASE ?? "").replace(/\/$/, "");

function apiUrl(path: string, params?: Record<string, string | number | undefined>): string {
  if (!path.startsWith("/")) path = "/" + path;
  const base = API_BASE ? `${API_BASE}${path}` : path;
  if (!params) return base;

  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }

  const qs = search.toString();
  return qs ? `${base}?${qs}` : base;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(detail || `API request failed: ${response.status}`);
  }

  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

async function apiGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const response = await fetch(apiUrl(path, params));
  return parseResponse<T>(response);
}

async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return parseResponse<T>(response);
}

async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return parseResponse<T>(response);
}

async function apiDelete(path: string): Promise<void> {
  const response = await fetch(apiUrl(path), {
    method: "DELETE",
  });
  await parseResponse<void>(response);
}

export interface AtlasMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface AtlasConversation {
  id: string;
  session_id: string | null;
  meeting_id: string | null;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface AtlasConversationDetail extends AtlasConversation {
  messages: AtlasMessage[];
}

export interface ConversationListResponse {
  items: AtlasConversation[];
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

export interface MeetingListParams {
  offset?: number;
  limit?: number;
  order_by?: string;
  order?: "asc" | "desc";
}

export function createConversation(params?: { meeting_id?: string; title?: string }) {
  return apiPost<AtlasConversationDetail>("/atlas/conversations", params);
}

export function listConversations() {
  return apiGet<ConversationListResponse>("/atlas/conversations");
}

export function getConversation(conversationId: string) {
  return apiGet<AtlasConversationDetail>(
    `/atlas/conversations/${encodeURIComponent(conversationId)}`,
  );
}

export function updateConversation(
  conversationId: string,
  params: { title?: string; meeting_id?: string; session_id?: string },
) {
  return apiPatch<AtlasConversationDetail>(
    `/atlas/conversations/${encodeURIComponent(conversationId)}`,
    params,
  );
}

export function deleteConversation(conversationId: string) {
  return apiDelete(`/atlas/conversations/${encodeURIComponent(conversationId)}`);
}

export function createMessage(conversationId: string, params: { role: string; content: string }) {
  return apiPost<AtlasMessage>(`/atlas/conversations/${encodeURIComponent(conversationId)}/messages`, params);
}

export function chatWithLLM(conversationId: string, params: { role: string; content: string }) {
  return apiPost<AtlasMessage>(`/atlas/conversations/${encodeURIComponent(conversationId)}/chat`, params);
}

export async function streamChat(
  conversationId: string,
  params: { role: string; content: string },
  onChunk: (text: string) => void,
  abortSignal?: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl(`/atlas/conversations/${encodeURIComponent(conversationId)}/chat/stream`), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(params),
    signal: abortSignal,
  });

  if (!response.ok) {
    throw new Error(`Failed to stream chat: ${response.status} ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("No reader available");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";

      for (const frame of frames) {
        for (const line of frame.split("\n")) {
          const trimmed = line.trimEnd();
          if (!trimmed.startsWith("data:")) continue;
          const raw = trimmed.slice(5).trimStart();
          if (!raw || raw === "[DONE]") continue;

          try {
            const data = JSON.parse(raw) as { text?: string; error?: string };
            if (data.text !== undefined) onChunk(data.text);
            if (data.error) throw new Error(data.error);
          } catch {
            // Match the integrated Atlas stream parser: malformed frames are ignored.
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export function getMeetings(params?: MeetingListParams) {
  return apiGet<{ items: MeetingListItem[]; total: number; offset: number; limit: number }>(
    "/meetings",
    params as Record<string, string | number | undefined> | undefined,
  );
}

export function getMeeting(meetingId: string) {
  return apiGet<MeetingDetail>(`/meetings/${encodeURIComponent(meetingId)}`);
}
