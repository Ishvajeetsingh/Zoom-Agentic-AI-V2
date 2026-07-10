import { API_BASE_URL, apiGet, apiPost, apiPatch, apiDelete } from "./client";

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

export function createConversation(params?: { meeting_id?: string; title?: string }) {
  return apiPost<AtlasConversationDetail>("/atlas/conversations", params);
}

export function listConversations() {
  return apiGet<ConversationListResponse>("/atlas/conversations");
}

export function getConversation(conversationId: string) {
  return apiGet<AtlasConversationDetail>(`/atlas/conversations/${conversationId}`);
}

export function updateConversation(
  conversationId: string,
  params: { title?: string; meeting_id?: string; session_id?: string }
) {
  return apiPatch<AtlasConversationDetail>(`/atlas/conversations/${conversationId}`, params);
}

export function deleteConversation(conversationId: string) {
  return apiDelete(`/atlas/conversations/${conversationId}`);
}

export function createMessage(conversationId: string, params: { role: string; content: string }) {
  return apiPost<AtlasMessage>(`/atlas/conversations/${conversationId}/messages`, params);
}

export function chatWithLLM(conversationId: string, params: { role: string; content: string }) {
  return apiPost<AtlasMessage>(`/atlas/conversations/${conversationId}/chat`, params);
}

export async function streamChat(
  conversationId: string,
  params: { role: string; content: string },
  onChunk: (text: string) => void,
  abortSignal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/atlas/conversations/${conversationId}/chat/stream`, {
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
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const match = trimmed.match(/^data: (.+)$/m);
        if (!match) continue;
        try {
          const data = JSON.parse(match[1]);
          if (data.text !== undefined) {
            onChunk(data.text);
          }
          if (data.error) {
            throw new Error(data.error);
          }
        } catch {
          // ignore malformed lines
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
