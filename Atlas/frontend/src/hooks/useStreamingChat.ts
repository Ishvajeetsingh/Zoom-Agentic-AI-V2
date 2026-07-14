import { useCallback, useEffect, useRef, useState } from "react";
import type { Citation, Message } from "@/types";
import { AtlasApiError, streamChat } from "@/lib/api";
import type { StreamFrame } from "@/lib/utils";

interface UseStreamingChatResult {
  messages: Message[];
  streaming: boolean;
  error: string | null;
  loadingConversation: boolean;
  loadConversation: (id: string) => Promise<void>;
  send: (text: string) => Promise<void>;
  stop: () => void;
  reset: () => void;
  clearError: () => void;
}

// Coerce a stream frame's optional citations field into Citation[].
function coerceCitations(value: unknown): Citation[] | undefined {
  if (!value) return undefined;
  if (Array.isArray(value)) {
    return value.filter(Boolean) as Citation[];
  }
  if (typeof value === "object") {
    const v = value as Record<string, unknown>;
    if (Array.isArray(v.citations)) return v.citations as Citation[];
    if (Array.isArray(v.sources)) return v.sources as Citation[];
  }
  return undefined;
}

let idCounter = 0;
function genId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${Date.now()}-${idCounter}`;
}

export function useStreamingChat(conversationId: string | null): UseStreamingChatResult {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const loadConversation = useCallback(async (id: string) => {
    setLoadingConversation(true);
    setError(null);
    try {
      const res = await fetch(
        `${(import.meta.env.VITE_ATLAS_API_BASE ?? "").replace(/\/$/, "")}/atlas/conversations/${encodeURIComponent(id)}`,
        { headers: { Accept: "application/json" } },
      );
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new AtlasApiError(`Atlas API ${res.status} ${res.statusText}`, res.status, body);
      }
      const data = await res.json();
      // Conversations carry their messages inline.
      const incoming: Message[] = Array.isArray(data.messages) ? data.messages : [];
      setMessages(
        incoming.map((m, i) => ({
          id: m.id ?? `loaded-${i}`,
          role: m.role,
          content: m.content ?? "",
          citations: m.citations,
          created_at: m.created_at,
        })),
      );
    } catch (e) {
      const msg = e instanceof AtlasApiError ? e.message : String(e);
      setError(msg);
      setMessages([]);
    } finally {
      setLoadingConversation(false);
    }
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  const send = useCallback(
    async (text: string) => {
      if (!conversationId) {
        setError("No conversation selected.");
        return;
      }
      if (streaming) return;
      setError(null);

      const userMsg: Message = {
        id: genId("user"),
        role: "user",
        content: text,
      };
      const assistantId = genId("assistant");
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const updateAssistant = (fn: (m: Message) => Message) =>
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? fn(m) : m)),
        );

      try {
        await streamChat(conversationId, { content: text }, {
          signal: controller.signal,
          onFrame: (frame: StreamFrame) => {
            const piece = typeof frame.text === "string" ? frame.text : "";
            const cits = coerceCitations(frame.citations);
            updateAssistant((m) => ({
              ...m,
              content: m.content + piece,
              citations: cits ?? m.citations,
            }));
          },
          onError: (err) => {
            if ((err as Error).name === "AbortError") return;
            const msg = err instanceof AtlasApiError ? err.message : String(err);
            setError(msg);
            updateAssistant((m) => ({
              ...m,
              content:
                m.content +
                (m.content ? "\n\n" : "") +
                `⚠️ ${msg}`,
            }));
          },
        });
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [conversationId, streaming],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setStreaming(false);
    setError(null);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  // Reset state when the active conversation changes.
  useEffect(() => {
    reset();
    if (conversationId) void loadConversation(conversationId);
    return () => {
      abortRef.current?.abort();
    };
  }, [conversationId, loadConversation, reset]);

  return {
    messages,
    streaming,
    error,
    loadingConversation,
    loadConversation,
    send,
    stop,
    reset,
    clearError,
  };
}
