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
  const response = await fetch(apiUrl(path, params), {
    headers: { Accept: "application/json" },
  });
  return parseResponse<T>(response);
}

async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body ? JSON.stringify({ payload: body }) : undefined,
  });
  return parseResponse<T>(response);
}

async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body ? JSON.stringify({ payload: body }) : undefined,
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

function normalizeMessage(message: Partial<AtlasMessage>, index: number, conversationId: string): AtlasMessage {
  return {
    id: message.id ?? `message-${index}`,
    conversation_id: message.conversation_id ?? conversationId,
    role: message.role === "assistant" ? "assistant" : "user",
    content: message.content ?? "",
    created_at: message.created_at ?? new Date().toISOString(),
  };
}

function normalizeConversation(conversation: Partial<AtlasConversationDetail>): AtlasConversationDetail {
  const id = conversation.id ?? "";
  const messages = Array.isArray(conversation.messages)
    ? conversation.messages.map((message, index) => normalizeMessage(message, index, id))
    : [];

  return {
    id,
    session_id: conversation.session_id ?? null,
    meeting_id: conversation.meeting_id ?? null,
    title: conversation.title ?? null,
    created_at: conversation.created_at ?? new Date().toISOString(),
    updated_at: conversation.updated_at ?? conversation.created_at ?? new Date().toISOString(),
    message_count: conversation.message_count ?? messages.length,
    messages,
  };
}

export async function createConversation(params?: { meeting_id?: string; title?: string }) {
  const conversation = await apiPost<AtlasConversationDetail>("/atlas/conversations", params);
  return normalizeConversation(conversation);
}

export async function listConversations(): Promise<ConversationListResponse> {
  const data = await apiGet<ConversationListResponse | AtlasConversation[]>("/atlas/conversations");
  const items = Array.isArray(data) ? data : data.items ?? [];
  return {
    items: items.map((conversation) => normalizeConversation(conversation)),
    total: Array.isArray(data) ? items.length : data.total ?? items.length,
    offset: Array.isArray(data) ? 0 : data.offset ?? 0,
    limit: Array.isArray(data) ? items.length : data.limit ?? items.length,
  };
}

export async function getConversation(conversationId: string) {
  const conversation = await apiGet<AtlasConversationDetail>(
    `/atlas/conversations/${encodeURIComponent(conversationId)}`,
  );
  return normalizeConversation(conversation);
}

export async function updateConversation(
  conversationId: string,
  params: { title?: string; meeting_id?: string; session_id?: string },
) {
  const conversation = await apiPatch<AtlasConversationDetail>(
    `/atlas/conversations/${encodeURIComponent(conversationId)}`,
    params,
  );
  return normalizeConversation(conversation);
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
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ payload: params }),
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
            onChunk(raw);
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
