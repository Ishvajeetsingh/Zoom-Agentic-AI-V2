import { useState, useEffect, useCallback, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AppShell } from "../components/layout/AppShell";
import { type AtlasConversation, type AtlasConversationDetail } from "../api/atlas";
import { useAtlasActions, groupConversationsByDate, getGreeting } from "../hooks/useAtlasActions";
import { getMeetings, getMeeting, type MeetingListItem, type MeetingDetail } from "../api/meetings";

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SUGGESTIONS = [
  { icon: "\u{1F4C4}", label: "Summarize a meeting", prompt: "Summarize the key points from this meeting." },
  { icon: "\u{1F9E0}", label: "Explain a concept", prompt: "Explain the main concept discussed in the meeting." },
  { icon: "\u2753", label: "Generate a quiz", prompt: "Generate a quiz based on the meeting content." },
  { icon: "\u{1F4CC}", label: "Find action items", prompt: "What are the action items from this meeting?" },
  { icon: "\u{1F4DA}", label: "Review learning outputs", prompt: "Review the learning outputs from this meeting." },
  { icon: "\u{1F4DD}", label: "Create study notes", prompt: "Create study notes from this meeting." },
];

type LoadingState =
  | "idle"
  | "connecting"
  | "loading_meetings"
  | "loading_conversations"
  | "loading_context"
  | "sending"
  | "preparing_response"
  | "updating_conversation"
  | "streaming";

type ErrorType = "network" | "backend" | "ollama" | "meeting" | "conversation" | "general";

interface AppError {
  type: ErrorType;
  title: string;
  message: string;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/* ------------------------------------------------------------------ */
/*  ChatMessage Component                                               */
/* ------------------------------------------------------------------ */

function UserAvatar() {
  return (
    <div className="atlas-avatar atlas-avatar-user" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8.5" r="3.6" />
        <path d="M5.5 19.5a6.5 6.5 0 0 1 13 0" />
      </svg>
    </div>
  );
}

function AssistantAvatar() {
  return (
    <div className="atlas-avatar atlas-avatar-assistant" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3.2 L13.9 9.1 L19.8 11 L13.9 12.9 L12 18.8 L10.1 12.9 L4.2 11 L10.1 9.1 Z" fill="currentColor" fillOpacity="0.22" strokeLinejoin="round" />
        <path d="M12 3.2 L13.9 9.1 L19.8 11 L13.9 12.9 L12 18.8 L10.1 12.9 L4.2 11 L10.1 9.1 Z" />
        <circle cx="12" cy="11" r="1.4" fill="currentColor" stroke="none" />
      </svg>
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="atlas-thinking-dots" aria-label="Thinking">
      <span className="atlas-thinking-dot" />
      <span className="atlas-thinking-dot" />
      <span className="atlas-thinking-dot" />
    </span>
  );
}

function ChatMessage({ content, role, createdAt, thinking }: { content: string; role: string; createdAt?: string; thinking?: boolean }) {
  const isUser = role === "user";
  return (
    <div className={`atlas-message ${role} ${thinking ? "atlas-message-thinking" : ""}`}>
      {isUser ? <UserAvatar /> : <AssistantAvatar />}
      <div className="atlas-message-body">
        <div className="atlas-message-sender">{isUser ? "You" : "Atlas"}</div>
        <div className="atlas-message-content">
          {thinking && !content ? (
            <div className="atlas-thinking-row">
              <span className="atlas-thinking-label">Thinking</span>
              <ThinkingDots />
            </div>
          ) : role === "assistant" ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          ) : (
            content
          )}
        </div>
        {createdAt && (
          <div className="atlas-message-time">
            {new Date(createdAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export function AtlasPage() {
  const actions = useAtlasActions();

  /* ---- Conversations ---- */
  const [conversations, setConversations] = useState<AtlasConversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AtlasConversationDetail["messages"]>([]);
  const [inputValue, setInputValue] = useState("");

  /* ---- Meetings ---- */
  const [meetings, setMeetings] = useState<MeetingListItem[]>([]);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [selectedMeeting, setSelectedMeeting] = useState<MeetingDetail | null>(null);

  /* ---- UI State ---- */
  const [loading, setLoading] = useState<LoadingState>("idle");
  const [error, setError] = useState<AppError | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  /* ---- Rename State ---- */
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  /* ---- Refs ---- */
  const isProcessingRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const shouldScrollRef = useRef(true);

  /* ---------------------------------------------------------------- */
  /*  Auto-scroll effect                                               */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    if (messagesEndRef.current && shouldScrollRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const threshold = 80;
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
    shouldScrollRef.current = nearBottom;
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Load meetings                                                    */
  /* ---------------------------------------------------------------- */

  const loadMeetings = useCallback(async () => {
    if (isProcessingRef.current) return;
    setLoading("loading_meetings");
    try {
      const res = await getMeetings({ limit: 100 });
      setMeetings(res.items);
    } catch (err) {
      setError({ type: "network", title: "Unable to load meetings", message: "Please check your connection and try again." });
    } finally {
      setLoading((prev) => (prev === "loading_meetings" ? "idle" : prev));
    }
  }, []);

  useEffect(() => {
    loadMeetings();
  }, [loadMeetings]);

  /* ---------------------------------------------------------------- */
  /*  Load conversations                                               */
  /* ---------------------------------------------------------------- */

  const loadConversations = useCallback(async () => {
    if (isProcessingRef.current) return;
    try {
      const res = await actions.listConversations();
      setConversations(res.items);
    } catch (err) {
      setError({ type: "backend", title: "Unable to load conversations", message: "The backend is temporarily unavailable. Please try again later." });
    }
  }, [actions]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  /* ---------------------------------------------------------------- */
  /*  Meeting detail loader                                            */
  /* ---------------------------------------------------------------- */

  const loadMeetingDetail = useCallback(async (meetingId: string | null) => {
    if (!meetingId) {
      setSelectedMeeting(null);
      return;
    }
    setLoading("loading_context");
    try {
      const detail = await getMeeting(meetingId);
      setSelectedMeeting(detail);
    } catch (err) {
      setError({ type: "meeting", title: "Meeting unavailable", message: "The selected meeting details could not be retrieved." });
      setSelectedMeeting(null);
    } finally {
      setLoading((prev) => (prev === "loading_context" ? "idle" : prev));
    }
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Initialize from stored state (recovery after refresh)            */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    // Always start on the Atlas landing page — do not auto-reopen the previous conversation.
    // Only the conversation history and meeting selection persist across page loads.
    localStorage.removeItem("atlas_active_conversation_id");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Persist active conversation on change                            */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    if (activeId) {
      localStorage.setItem("atlas_active_conversation_id", activeId);
    } else {
      localStorage.removeItem("atlas_active_conversation_id");
    }
  }, [activeId]);

  /* ---------------------------------------------------------------- */
  /*  Conversation actions                                               */
  /* ---------------------------------------------------------------- */

  const handleNewChat = useCallback(async () => {
    if (isProcessingRef.current) return;
    isProcessingRef.current = true;
    setLoading("connecting");
    setError(null);
    try {
      const conv = await actions.createConversation({
        title: "New Chat",
        meeting_id: selectedMeetingId ?? undefined,
      });
      setConversations((prev) => [conv, ...prev]);
      setActiveId(conv.id);
      if (conv.meeting_id) {
        setSelectedMeetingId(conv.meeting_id);
        await loadMeetingDetail(conv.meeting_id);
      } else {
        setSelectedMeetingId(null);
        setSelectedMeeting(null);
      }
      setMessages([]);
    } catch (err) {
      setError({ type: "backend", title: "Failed to create chat", message: "We couldn't start a new conversation. Please try again." });
    } finally {
      setLoading("idle");
      isProcessingRef.current = false;
    }
  }, [actions, loadMeetingDetail, selectedMeetingId]);

  const handleSelectConversation = useCallback(async (id: string) => {
    if (isProcessingRef.current) return;
    isProcessingRef.current = true;
    setLoading("loading_conversations");
    setError(null);
    try {
      const conv = await actions.getConversation(id);
      setActiveId(id);
      if (conv.meeting_id) {
        setSelectedMeetingId(conv.meeting_id);
        await loadMeetingDetail(conv.meeting_id);
      } else {
        setSelectedMeetingId(null);
        setSelectedMeeting(null);
      }
      setMessages(conv.messages);
    } catch (err) {
      setError({ type: "conversation", title: "Conversation unavailable", message: "We couldn't load this conversation. It may have been deleted." });
      setActiveId(null);
      setSelectedMeetingId(null);
      setSelectedMeeting(null);
    } finally {
      setLoading("idle");
      isProcessingRef.current = false;
    }
  }, [actions, loadMeetingDetail]);

  const handleDelete = useCallback(async (id: string) => {
    if (isProcessingRef.current) return;
    if (!window.confirm("Are you sure you want to delete this conversation? This action cannot be undone.")) return;
    try {
      await actions.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
        setSelectedMeetingId(null);
        setSelectedMeeting(null);
        localStorage.removeItem("atlas_active_conversation_id");
      }
    } catch (err) {
      setError({ type: "backend", title: "Failed to delete conversation", message: "Please try again later." });
    }
  }, [actions, activeId]);

  const handleRename = useCallback(async (id: string, newTitle: string) => {
    if (isProcessingRef.current) return;
    try {
      await actions.updateConversation(id, { title: newTitle });
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title: newTitle } : c))
      );
    } catch (err) {
      setError({ type: "backend", title: "Failed to rename", message: "Please try again later." });
    }
  }, [actions]);

  /* ---------------------------------------------------------------- */
  /*  Meeting selection handler                                          */
  /* ---------------------------------------------------------------- */

  const handleMeetingChange = useCallback(async (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newMeetingId = event.target.value || null;
    setSelectedMeetingId(newMeetingId);
    setError(null);
    if (newMeetingId) {
      await loadMeetingDetail(newMeetingId);
    } else {
      setSelectedMeeting(null);
    }
    // If a conversation is active, update its meeting_id
    if (activeId) {
      setLoading("updating_conversation");
      try {
        await actions.updateConversation(activeId, { meeting_id: newMeetingId ?? undefined });
        setConversations((prev) =>
          prev.map((c) => (c.id === activeId ? { ...c, meeting_id: newMeetingId } : c))
        );
      } catch (err) {
        setError({ type: "backend", title: "Failed to update meeting link", message: "The conversation was not updated. Please try again." });
      } finally {
        setLoading("idle");
      }
    }
  }, [activeId, actions, loadMeetingDetail]);

  /* ---------------------------------------------------------------- */
  /*  Title generation                                                   */
  /* ---------------------------------------------------------------- */

  const generateTitleFromMessage = useCallback((message: string): string => {
    const MAX_LEN = 30;
    const FILLERS = new Set([
      "please", "can", "you", "could", "would", "the", "a", "an", "and", "or",
      "of", "for", "to", "in", "on", "at", "from", "with", "based", "this",
      "that", "these", "those", "my", "me", "i", "is", "are", "be", "about",
      "as", "it", "its", "what", "which", "how", "why", "who", "when", "where",
      "do", "did", "does", "have", "has", "had", "will", "shall", "should",
      "now", "then", "just", "also", "very", "really", "kindly",
    ]);

    const trimmed = message.trim();
    if (!trimmed) return "New Chat";

    let tokens = trimmed
      .replace(/[^a-zA-Z0-9\s-]/g, " ")
      .split(/\s+/)
      .map((t) => t.trim())
      .filter((t) => t.length > 0);

    const cleaned: string[] = [];
    for (let i = 0; i < tokens.length; i++) {
      const lower = tokens[i].toLowerCase();
      if (FILLERS.has(lower)) {
        // keep a filler only when it leads with another meaningful token
        if (i === 0 || cleaned.length === 0) continue;
        const next = tokens[i + 1];
        if (!next) continue;
        if (FILLERS.has(next.toLowerCase())) continue;
      }
      const word = tokens[i];
      const c = cleaned.length === 0
        ? word.charAt(0).toUpperCase() + word.slice(1)
        : word.toLowerCase();
      cleaned.push(c);
    }

    if (cleaned.length === 0) return "New Chat";

    let title = "";
    for (const w of cleaned) {
      const candidate = title ? `${title} ${w}` : w;
      if (candidate.length > MAX_LEN) break;
      title = candidate;
    }

    if (!title) title = cleaned.join(" ").slice(0, MAX_LEN);

    // De-duplicate trailing punctuation
    title = title.replace(/([.!?])\1+$/, "$1").replace(/\s+([.!?])/g, "$1").trim();

    if (title.length > MAX_LEN) {
      // Shrink to the last space boundary <= MAX_LEN without splitting words
      const sub = title.slice(0, MAX_LEN + 1);
      const lastSpace = sub.lastIndexOf(" ");
      title = lastSpace > 0 ? sub.slice(0, lastSpace) : title.slice(0, MAX_LEN);
      title = title.replace(/[,;:]$/, "");
    }

    return title || "New Chat";
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Send handler                                                       */
  /* ---------------------------------------------------------------- */

  const handleSend = useCallback(async (overrideText?: string) => {
    // Allow callers (e.g. landing-page quick actions) to send a prompt
    // immediately WITHOUT first populating the input box. When overrideText
    // is provided it is treated as the user message verbatim and the input
    // field is left untouched. Otherwise we fall back to inputValue (Send).
    const override = typeof overrideText === "string" ? overrideText.trim() : "";
    const text = (override || inputValue.trim());
    if (!text || isProcessingRef.current) return;
    isProcessingRef.current = true;

    // Cancel any in-progress stream and clean up previous temporary assistant
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (loading === "streaming") {
      setMessages((prev) => prev.filter((msg) => !msg.id.startsWith("stream-")));
    }

    setError(null);

    let convId = activeId;

    // Create a new conversation if none is active
    if (!convId) {
      setLoading("connecting");
      try {
        const conv = await actions.createConversation({
          title: "New Chat",
          meeting_id: selectedMeetingId ?? undefined,
        });
        convId = conv.id;
        setConversations((prev) => [conv, ...prev]);
        setActiveId(conv.id);
        if (conv.meeting_id) {
          setSelectedMeetingId(conv.meeting_id);
          await loadMeetingDetail(conv.meeting_id);
        }
      } catch (err) {
        setError({ type: "backend", title: "Failed to start conversation", message: "We couldn't create a new chat. Please try again." });
        isProcessingRef.current = false;
        setLoading("idle");
        return;
      }
    }

    // Optimistic UI update
    const tempMessage: typeof messages[0] = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
      conversation_id: convId!,
    };
    setMessages((prev) => [...prev, tempMessage]);
    setInputValue("");
    setLoading("streaming");
    shouldScrollRef.current = true;

    // Add temporary streaming assistant message
    const streamAssistantId = `stream-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      {
        id: streamAssistantId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        conversation_id: convId!,
      },
    ]);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      await actions.streamChat(convId!, { role: "user", content: text }, (chunk: string) => {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === streamAssistantId
              ? { ...msg, content: msg.content + chunk }
              : msg
          )
        );
      }, controller.signal);

      const updatedConv = await actions.getConversation(convId!);
      setMessages(updatedConv.messages);

      // Update conversation list with new updated_at
      setConversations((prev) =>
        prev.map((c) => (c.id === convId ? { ...c, updated_at: updatedConv.updated_at } : c))
      );

      // Auto-generate title if currently "New Chat" and this is the first user message
      const userMessageCount = updatedConv.messages.filter((m) => m.role === "user").length;
      if ((updatedConv.title === "New Chat" || !updatedConv.title) && userMessageCount === 1) {
        const generatedTitle = generateTitleFromMessage(text);
        await actions.updateConversation(convId!, { title: generatedTitle });
        setConversations((prev) =>
          prev.map((c) => (c.id === convId ? { ...c, title: generatedTitle } : c))
        );
      }
    } catch (err) {
      // Remove only the temporary assistant message, keep the user's message
      setMessages((prev) => prev.filter((msg) => !msg.id.startsWith("stream-")));
      // Restore the input so the user can retry — but ONLY when the message
      // originated from the input box. Quick-action (overrideText) send paths
      // must never dump the prompt back into the input field.
      if (!override) {
        setInputValue(text);
      }
      setError({ type: "ollama", title: "Atlas is unavailable", message: "We're having trouble connecting to Atlas. Please try again in a moment." });
    } finally {
      abortControllerRef.current = null;
      setLoading("idle");
      isProcessingRef.current = false;
    }
  }, [inputValue, activeId, actions, selectedMeetingId, loadMeetingDetail, generateTitleFromMessage]);

  /* ---------------------------------------------------------------- */
  /*  Dismiss error                                                      */
  /* ---------------------------------------------------------------- */

  const dismissError = useCallback(() => setError(null), []);

  /* ---------------------------------------------------------------- */
  /*  Derived data                                                       */
  /* ---------------------------------------------------------------- */

  const filteredConversations = searchQuery.trim()
    ? conversations.filter((c) => (c.title ?? "").toLowerCase().includes(searchQuery.toLowerCase()))
    : conversations;

  const grouped = groupConversationsByDate(filteredConversations);

  /* ---------------------------------------------------------------- */
  /*  Loading text helper                                                */
  /* ---------------------------------------------------------------- */

  const getLoadingText = () => {
    switch (loading) {
      case "connecting": return "Connecting Atlas...";
      case "loading_meetings": return "Loading meetings...";
      case "loading_conversations": return "Loading conversations...";
      case "loading_context": return "Loading meeting context...";
      case "sending": return "Sending...";
      case "preparing_response": return "Preparing educational response...";
      case "updating_conversation": return "Updating conversation...";
      case "streaming": return "Atlas is typing...";
      default: return "Loading...";
    }
  };

  /* ---------------------------------------------------------------- */
  /*  Render                                                             */
  /* ---------------------------------------------------------------- */

  return (
    <AppShell>
      <div className="atlas-page">
        {/* Left Sidebar */}
        <aside className="atlas-sidebar">
          <div className="atlas-sidebar-header">
            <button className="atlas-new-chat-btn" onClick={handleNewChat} disabled={isProcessingRef.current}>
              + New Chat
            </button>
            <input
              className="atlas-search-input"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="atlas-conversation-list">
            {Object.entries(grouped).map(([group, items]) =>
              items.length > 0 ? (
                <div key={group} className="atlas-group">
                  <div className="atlas-group-title">{group}</div>
                  {items.map((conv) => (
                    <div
                      key={conv.id}
                      className={`atlas-conversation-item ${activeId === conv.id ? "active" : ""}`}
                      onClick={() => handleSelectConversation(conv.id)}
                    >
                      {editingId === conv.id ? (
                        <input
                          className="atlas-rename-input"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              if (editValue.trim()) handleRename(conv.id, editValue.trim());
                              setEditingId(null);
                            }
                            if (e.key === "Escape") {
                              setEditingId(null);
                              setEditValue("");
                            }
                          }}
                          onBlur={() => {
                            if (editValue.trim()) handleRename(conv.id, editValue.trim());
                            setEditingId(null);
                          }}
                          autoFocus
                        />
                      ) : (
                        <div className="atlas-conversation-title">
                          {conv.title || "Untitled Chat"}
                        </div>
                      )}
                      <div className="atlas-conversation-actions">
                        <span className="atlas-conversation-count">{conv.message_count}</span>
                        <button
                          className="atlas-conversation-action"
                          onClick={(e) => { e.stopPropagation(); setEditingId(conv.id); setEditValue(conv.title || "Untitled Chat"); }}
                          title="Rename"
                        >
                          ✎
                        </button>
                        <button
                          className="atlas-conversation-action"
                          onClick={(e) => { e.stopPropagation(); handleDelete(conv.id); }}
                          title="Delete"
                        >
                          &times;
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null
            )}
          </div>
        </aside>

        {/* Center Chat */}
        <main className="atlas-chat">
          {/* Loading / Error overlays */}
          {error && (
            <div className="atlas-error-banner">
              <div className="atlas-error-content">
                <div className="atlas-error-title">{error.title}</div>
                <div className="atlas-error-message">{error.message}</div>
              </div>
              <button className="atlas-error-dismiss" onClick={dismissError}>Dismiss</button>
            </div>
          )}

          {loading !== "idle" && loading !== "sending" && loading !== "streaming" && (
            <div className="atlas-loading-overlay">
              <div className="atlas-loading-spinner" />
              <div className="atlas-loading-text">{getLoadingText()}</div>
            </div>
          )}

          {!activeId || messages.length === 0 ? (
            <div className="atlas-hero">
              <div className="atlas-hero-greeting">{getGreeting()}</div>
              <h1 className="atlas-hero-title">Atlas</h1>
              <div className="atlas-hero-subtitle">Meeting Intelligence Assistant</div>
              <p className="atlas-hero-desc">
                I'm Atlas, your Meeting Intelligence Assistant. I can help you understand
                meetings, explore learning material, generate quizzes, explain concepts, and
                answer questions.
              </p>
              {!selectedMeetingId && (
                <div className="atlas-no-meeting-banner">
                  No meeting selected. Select a meeting to activate Atlas intelligence.
                </div>
              )}
              <div className="atlas-suggestion-grid">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.label}
                    className="atlas-suggestion-card"
                    onClick={() => handleSend(s.prompt)}
                  >
                    <span className="atlas-suggestion-icon">{s.icon}</span>
                    <span className="atlas-suggestion-label">{s.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="atlas-chat-messages" onScroll={handleScroll} ref={messagesContainerRef}>
              {messages.map((msg) => {
                const isStreaming = msg.id.startsWith("stream-");
                const thinking = isStreaming && (!msg.content || msg.content.length === 0);
                return (
                  <ChatMessage
                    key={msg.id}
                    role={msg.role}
                    content={msg.content}
                    createdAt={isStreaming ? undefined : msg.created_at}
                    thinking={thinking}
                  />
                );
              })}
              <div ref={messagesEndRef} />
            </div>
          )}

          <div className="atlas-chat-input-area">
            <textarea
              className="atlas-chat-input"
              placeholder="Ask Atlas anything..."
              rows={2}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={isProcessingRef.current}
            />
              <button className="atlas-chat-send" onClick={() => handleSend()} disabled={isProcessingRef.current || !inputValue.trim()}>
              {isProcessingRef.current ? "..." : "Send"}
            </button>
          </div>
        </main>

        {/* Right Context Panel */}
        <aside className={`atlas-context-panel ${rightPanelOpen ? "open" : ""}`}>
          <div className="atlas-context-header">
            <h3>Context</h3>
            <button className="atlas-context-toggle" onClick={() => setRightPanelOpen(!rightPanelOpen)}>
              {rightPanelOpen ? "Collapse" : "Expand"}
            </button>
          </div>
          {rightPanelOpen && (
            <div className="atlas-context-body">
              {/* Meeting selector */}
              <div className="atlas-context-section">
                <h4>Meeting</h4>
                <select
                  className="atlas-meeting-select"
                  value={selectedMeetingId ?? ""}
                  onChange={handleMeetingChange}
                >
                  <option value="">-- Select a meeting --</option>
                {meetings
                  .slice()
                  .sort((a, b) => {
                    const da = a.created_at ? new Date(a.created_at).getTime() : 0;
                    const db = b.created_at ? new Date(b.created_at).getTime() : 0;
                    return db - da;
                  })
                  .map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.topic || "Untitled Meeting"}
                    </option>
                  ))}
                </select>
              </div>

              {/* Current meeting info */}
              {selectedMeeting && (
                <div className="atlas-context-section atlas-meeting-info">
                  <h4>Current Meeting</h4>
                  <div className="atlas-meeting-title">{selectedMeeting.topic || "Untitled Meeting"}</div>
                  <div className="atlas-meeting-date">{formatDate(selectedMeeting.start_time)}</div>
                  <div className="atlas-meeting-duration">{selectedMeeting.duration_minutes ? `${selectedMeeting.duration_minutes} min` : ""}</div>
                </div>
              )}

              {/* Status badges */}
              {selectedMeeting && (
                <div className="atlas-context-section">
                  <h4>Status</h4>
                  <div className="atlas-status-badges">
                    {selectedMeeting.transcript_count > 0 ? (
                      <span className="atlas-badge success">Transcript Ready</span>
                    ) : (
                      <span className="atlas-badge warning">Transcript Pending</span>
                    )}
                    {selectedMeeting.question_count > 0 ? (
                      <span className="atlas-badge success">Questions Generated</span>
                    ) : (
                      <span className="atlas-badge warning">Questions Pending</span>
                    )}
                    {selectedMeeting.transcript_count > 0 && selectedMeeting.question_count > 0 && (
                      <span className="atlas-badge success">Insights Available</span>
                    )}
                  </div>
                </div>
              )}

              {/* Contextual feedback */}
              {selectedMeetingId && !selectedMeeting && loading !== "loading_context" && (
                <div className="atlas-context-section">
                  <p className="atlas-context-placeholder">Meeting details unavailable.</p>
                </div>
              )}

              {selectedMeetingId && selectedMeeting && selectedMeeting.question_count === 0 && (
                <div className="atlas-context-section">
                  <p className="atlas-context-hint">Learning material is still being generated. Atlas will answer using whatever information currently exists.</p>
                </div>
              )}
            </div>
          )}
        </aside>
      </div>
    </AppShell>
  );
}
