import { useMemo } from "react";
import { type AtlasConversation, createConversation, listConversations, getConversation, updateConversation, deleteConversation, chatWithLLM, streamChat } from "../api/atlas";

export function useAtlasActions() {
  return useMemo(
    () => ({
      createConversation,
      listConversations,
      getConversation,
      updateConversation,
      deleteConversation,
      chatWithLLM,
      streamChat,
    }),
    []
  );
}

export function groupConversationsByDate(conversations: AtlasConversation[]) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart);
  yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  const weekStart = new Date(todayStart);
  weekStart.setDate(weekStart.getDate() - 7);

  const groups: Record<string, AtlasConversation[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    Older: [],
  };

  for (const conv of conversations) {
    const d = new Date(conv.updated_at);
    if (d >= todayStart) {
      groups.Today.push(conv);
    } else if (d >= yesterdayStart) {
      groups.Yesterday.push(conv);
    } else if (d >= weekStart) {
      groups["Previous 7 Days"].push(conv);
    } else {
      groups.Older.push(conv);
    }
  }

  return groups;
}

export function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good Morning.";
  if (hour < 18) return "Good Afternoon.";
  return "Good Evening.";
}
