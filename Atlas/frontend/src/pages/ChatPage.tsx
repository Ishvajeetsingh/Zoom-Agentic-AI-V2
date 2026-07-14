import { useState } from "react";
import { useConversations } from "@/hooks/useConversations";
import { useStreamingChat } from "@/hooks/useStreamingChat";
import { useTheme } from "@/hooks/useTheme";
import { Sidebar } from "@/components/Sidebar";
import { ChatComposer } from "@/components/ChatComposer";
import { ChatHeader } from "@/components/ChatHeader";
import { MessageList } from "@/components/MessageList";
import { EmptyState } from "@/components/EmptyState";
import type { Conversation } from "@/types";
import { classNames } from "@/lib/utils";

export function ChatPage() {
  const { theme, toggle: toggleTheme } = useTheme();
  const {
    conversations,
    loading: conversationsLoading,
    error: conversationsError,
    refresh,
    create,
    rename,
    remove,
    clearError: clearConvError,
  } = useConversations();

  const [activeId, setActiveId] = useState<string | null>(null);
  const [narrowOpen, setNarrowOpen] = useState(false);

  const {
    messages,
    streaming,
    error: chatError,
    loadingConversation,
    send,
    stop,
    clearError: clearChatError,
  } = useStreamingChat(activeId);

  const activeConversation: Conversation | null =
    conversations.find((c) => c.id === activeId) ?? null;

  const handleCreate = async () => {
    try {
      const c = await create("New chat");
      setActiveId(c.id);
      setNarrowOpen(false);
    } catch {
      // surfaced via conversationsError
    }
  };

  const handleSelect = (id: string) => {
    setActiveId(id);
    setNarrowOpen(false);
  };

  const handleRename = async (id: string, title: string) => {
    try {
      await rename(id, title);
    } catch {
      // surfaced via conversationsError
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await remove(id);
      if (activeId === id) setActiveId(null);
    } catch {
      // surfaced via conversationsError
    }
  };

  const onSend = async (text: string) => {
    // If no conversation is selected, create one on the fly before sending.
    let id = activeId;
    if (!id) {
      try {
        // Derive a reasonable title from the first prompt.
        const title = text.length > 40 ? `${text.slice(0, 40)}…` : text;
        const c = await create(title);
        id = c.id;
        setActiveId(c.id);
      } catch {
        return;
      }
    }
    // The hook is keyed on `activeId`, so on the rare path where we just
    // created a conversation, defer the send until the effect swaps it in.
    if (id !== activeId) {
      // Allow one render cycle for the hook to pick up the new id.
      setTimeout(() => void send(text), 0);
      return;
    }
    await send(text);
  };

  const mergedError = chatError ?? conversationsError;
  const dismissError = () => {
    clearChatError();
    clearConvError();
  };

  return (
    <div className={classNames("app", !narrowOpen && "app--narrow", narrowOpen && "app--sidebar-open")}>
      <div className="app__sidebar">
        <Sidebar
          conversations={conversations}
          activeId={activeId}
          loading={conversationsLoading}
          onSelect={handleSelect}
          onCreate={handleCreate}
          onRename={handleRename}
          onDelete={handleDelete}
          onOpenMenu={() => setNarrowOpen(true)}
        />
        <div className="sidebar__footer">
          <span>
            {conversations.length} conversation{conversations.length === 1 ? "" : "s"}
          </span>
          <button
            type="button"
            className="sidebar__icon-btn sidebar__theme-btn"
            onClick={toggleTheme}
            aria-label="Toggle theme"
            title={theme === "dark" ? "Light mode" : "Dark mode"}
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
          <button
            type="button"
            className="sidebar__icon-btn"
            onClick={refresh}
            aria-label="Refresh"
            title="Refresh conversations"
          >
            ⟳
          </button>
        </div>
      </div>

      <main className="chat">
        <ChatHeader
          conversation={activeConversation}
          onRename={(title) => activeId && handleRename(activeId, title)}
          onDelete={() => activeId && handleDelete(activeId)}
          onOpenSidebar={() => setNarrowOpen(true)}
        />

        {activeConversation ? (
          <MessageList
            messages={messages}
            streamingAssistantId={streaming ? messages.at(-1)?.id : null}
            error={mergedError}
            onDismissError={dismissError}
          />
        ) : (
          <div className="chat__messages">
            {mergedError && (
              <div className="error-banner" role="alert" style={{ maxWidth: 780, margin: "16px auto" }}>
                <span aria-hidden>!</span>
                <span style={{ flex: 1 }}>{mergedError}</span>
                <button type="button" className="error-banner__close" onClick={dismissError}>×</button>
              </div>
            )}
            {loadingConversation ? (
              <div className="chat__empty">
                <div style={{ display: "flex", gap: 8, alignItems: "center", color: "var(--fg-muted)" }}>
                  <span className="spinner" /> Loading conversation…
                </div>
              </div>
            ) : (
              <EmptyState onCreate={handleCreate} />
            )}
          </div>
        )}

        <ChatComposer onSend={onSend} onStop={stop} streaming={streaming} />
      </main>

      {narrowOpen && (
        <div className="app__scrim" onClick={() => setNarrowOpen(false)} aria-hidden />
      )}
    </div>
  );
}
