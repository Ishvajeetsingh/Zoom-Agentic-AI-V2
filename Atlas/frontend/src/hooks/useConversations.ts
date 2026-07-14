import { useCallback, useEffect, useState } from "react";
import type { Conversation } from "@/types";
import {
  AtlasApiError,
  createConversation,
  deleteConversation,
  listConversations,
  renameConversation,
} from "@/lib/api";

interface UseConversationsResult {
  conversations: Conversation[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  create: (title?: string) => Promise<Conversation>;
  rename: (id: string, title: string) => Promise<Conversation>;
  remove: (id: string) => Promise<void>;
  clearError: () => void;
}

export function useConversations(): UseConversationsResult {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listConversations();
      setConversations(list);
    } catch (e) {
      setError(e instanceof AtlasApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(
    async (title?: string) => {
      setError(null);
      try {
        const created = await createConversation({ title: title ?? "New chat" });
        setConversations((prev) => {
          const next = [created, ...prev];
          // Sort newest first if update order is not guaranteed by backend.
          return next;
        });
        return created;
      } catch (e) {
        const msg = e instanceof AtlasApiError ? e.message : String(e);
        setError(msg);
        throw e;
      }
    },
    [],
  );

  const rename = useCallback(async (id: string, title: string) => {
    setError(null);
    try {
      const updated = await renameConversation(id, title);
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title: updated.title ?? title } : c)),
      );
      return updated;
    } catch (e) {
      const msg = e instanceof AtlasApiError ? e.message : String(e);
      setError(msg);
      throw e;
    }
  }, []);

  const remove = useCallback(async (id: string) => {
    setError(null);
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
    } catch (e) {
      const msg = e instanceof AtlasApiError ? e.message : String(e);
      setError(msg);
      throw e;
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { conversations, loading, error, refresh, create, rename, remove, clearError };
}
