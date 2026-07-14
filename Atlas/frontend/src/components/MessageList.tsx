import { useEffect, useRef } from "react";
import type { Message } from "@/types";
import { MessageRow } from "./MessageRow";
import { ErrorBanner } from "./ErrorBanner";

interface MessageListProps {
  messages: Message[];
  streamingAssistantId?: string | null;
  error?: string | null;
  onDismissError?: () => void;
}

export function MessageList({
  messages,
  streamingAssistantId,
  error,
  onDismissError,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  // Track whether the user has scrolled away from the bottom.
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    stickToBottomRef.current = atBottom;
  };

  // Auto-scroll to bottom when new content arrives (if user is near bottom).
  useEffect(() => {
    if (stickToBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, streamingAssistantId]);

  return (
    <div className="chat__messages" ref={scrollRef} onScroll={onScroll}>
      <div className="chat__messages-inner">
        {error && (
          <ErrorBanner message={error} onDismiss={onDismissError} />
        )}
        {messages.map((m) => (
          <MessageRow
            key={m.id ?? `${m.role}-${m.created_at ?? ""}-${m.content.length}`}
            message={m}
            streaming={m.id != null && m.id === streamingAssistantId}
          />
        ))}
      </div>
      <div ref={bottomRef} />
    </div>
  );
}
