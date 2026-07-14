// Atlas HTTP client (browser side).
//
// Talks ONLY to the standalone Atlas backend. In dev the Vite proxy maps
// "/atlas" and "/health" to the backend; in production requests are made
// against VITE_ATLAS_API_BASE. The frontend never references Zoom Agentic AI.

import type {
  ChatRequestPayload,
  Conversation,
  ConversationListResponse,
  CreateConversationPayload,
  Message,
} from "@/types";
import { parseStreamFrame, type StreamFrame } from "./utils";

const API_BASE = (import.meta.env.VITE_ATLAS_API_BASE ?? "").replace(/\/$/, "");

// In dev we prefer relative URLs (the Vite proxy handles them). In prod we
// use the configured base. An empty API_BASE means "use relative URLs".
export function baseUrl(): string {
  return API_BASE;
}

function apiUrl(path: string): string {
  if (!path.startsWith("/")) path = "/" + path;
  return API_BASE ? `${API_BASE}${path}` : path;
}

export class AtlasApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "AtlasApiError";
    this.status = status;
    this.body = body;
  }
}

async function parseResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      try {
        body = await res.text();
      } catch {
        body = null;
      }
    }
    throw new AtlasApiError(
      `Atlas API ${res.status} ${res.statusText}`,
      res.status,
      body,
    );
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

// ---------------------------------------------------------------------------
// Conversation CRUD
// ---------------------------------------------------------------------------
export async function listConversations(): Promise<Conversation[]> {
  const res = await fetch(apiUrl("/atlas/conversations"), {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  const data = await parseResponse<ConversationListResponse | Conversation[]>(res);
  if (Array.isArray(data)) return data;
  return data?.items ?? data?.conversations ?? [];
}

export async function getConversation(id: string): Promise<Conversation> {
  const res = await fetch(apiUrl(`/atlas/conversations/${encodeURIComponent(id)}`), {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return parseResponse<Conversation>(res);
}

export async function createConversation(
  payload: CreateConversationPayload,
): Promise<Conversation> {
  // The backend router wraps the body under "payload"; send the user-facing
  // shape directly and let the backend forward what it needs.
  const res = await fetch(apiUrl("/atlas/conversations"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      payload: { title: payload.title ?? "New conversation", ...payload },
    }),
  });
  return parseResponse<Conversation>(res);
}

export async function renameConversation(
  id: string,
  title: string,
): Promise<Conversation> {
  const res = await fetch(apiUrl(`/atlas/conversations/${encodeURIComponent(id)}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ payload: { title } }),
  });
  return parseResponse<Conversation>(res);
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(apiUrl(`/atlas/conversations/${encodeURIComponent(id)}`), {
    method: "DELETE",
  });
  await parseResponse<void>(res);
}

export async function addMessage(
  id: string,
  payload: Record<string, unknown>,
): Promise<Message> {
  const res = await fetch(
    apiUrl(`/atlas/conversations/${encodeURIComponent(id)}/messages`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ payload }),
    },
  );
  return parseResponse<Message>(res);
}

// ---------------------------------------------------------------------------
// Non-streaming chat (kept for completeness; the UI uses streaming).
// ---------------------------------------------------------------------------
export async function chat(
  id: string,
  payload: ChatRequestPayload,
): Promise<Message> {
  const res = await fetch(
    apiUrl(`/atlas/conversations/${encodeURIComponent(id)}/chat`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ payload }),
    },
  );
  return parseResponse<Message>(res);
}

// ---------------------------------------------------------------------------
// Streaming chat (SSE over ReadableStream). No buffering — each parsed
// frame is yielded to the caller immediately.
// ---------------------------------------------------------------------------

export interface StreamCallbacks {
  onFrame?: (frame: StreamFrame, raw: string) => void;
  onError?: (err: AtlasApiError | Error) => void;
  signal?: AbortSignal;
}

/**
 * Open `POST /atlas/conversations/{id}/chat/stream` and iterate the upstream
 * SSE frames. The Atlas backend proxies the baseline's `text/event-stream`
 * byte-for-byte; here we decode frames as they arrive and invoke `onFrame`
 * for every `data:` line. We do NOT buffer the full body — the consumer
 * renders tokens as soon as they arrive.
 */
export async function streamChat(
  id: string,
  payload: ChatRequestPayload,
  callbacks: StreamCallbacks,
): Promise<void> {
  const { onFrame, onError, signal } = callbacks;
  let res: Response;
  try {
    res = await fetch(
      apiUrl(`/atlas/conversations/${encodeURIComponent(id)}/chat/stream`),
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ payload }),
        signal,
      },
    );
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    onError?.(e as Error);
    return;
  }

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.text();
    } catch {
      body = null;
    }
    onError?.(
      new AtlasApiError(`chat/stream ${res.status} ${res.statusText}`, res.status, body),
    );
    return;
  }

  if (!res.body) {
    onError?.(new AtlasApiError("No response body for chat/stream", res.status, null));
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line (\n\n). Emit complete frames
      // immediately and keep any partial trailing bytes in the buffer.
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        for (const line of frame.split("\n")) {
          const trimmed = line.trimEnd();
          // SSE supports multiple fields; we only forward `data:` lines.
          if (!trimmed.startsWith("data:")) continue;
          const raw = trimmed.slice(5).trimStart();
          if (raw === "[DONE]") return;
          const parsed = parseStreamFrame(raw);
          if (parsed) onFrame?.(parsed, raw);
        }
      }
    }
    // Flush a final frame if the upstream ended without a trailing blank line.
    if (buffer.trim()) {
      for (const line of buffer.split("\n")) {
        const trimmed = line.trimEnd();
        if (!trimmed.startsWith("data:")) continue;
        const raw = trimmed.slice(5).trimStart();
        if (raw === "[DONE]") return;
        const parsed = parseStreamFrame(raw);
        if (parsed) onFrame?.(parsed, raw);
      }
    }
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    onError?.(e as Error);
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ignore — already released
    }
  }
}
