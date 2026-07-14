// Domain types for the Atlas frontend.
//
// These mirror the JSON shapes returned by the standalone Atlas backend
// (which itself forwards Zoom Agentic AI responses). The frontend knows
// nothing about Zoom Agentic AI internals — only these wire shapes.

export type Role = "user" | "assistant" | "system";

export interface Citation {
  // Free-form metadata forwarded by the backend. We render anything we
  // recognise (id, source, snippet, url) and ignore the rest.
  id?: string | number;
  source?: string;
  snippet?: string;
  url?: string;
  [key: string]: unknown;
}

export interface Message {
  id?: string;
  role: Role;
  content: string;
  // Optional citations attached to assistant messages.
  citations?: Citation[];
  // ISO timestamp string from the backend, if present.
  created_at?: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  // Inline message history returned by GET /atlas/conversations/{id}.
  messages?: Message[];
  // Optional counts the backend may surface.
  message_count?: number;
}

export interface ConversationListResponse {
  items?: Conversation[];
  // Some backends return a raw list; we normalise in the client.
  conversations?: Conversation[];
  total?: number;
  [key: string]: unknown;
}

export interface CreateConversationPayload {
  title?: string;
  meeting_id?: string;
  [key: string]: unknown;
}

export interface ChatRequestPayload {
  content: string;
  [key: string]: unknown;
}
