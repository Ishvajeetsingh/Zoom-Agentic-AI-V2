import type { Message } from "@/types";
import { Markdown } from "./Markdown";
import { Citations } from "./Citations";
import { TypingIndicator } from "./TypingIndicator";

interface MessageRowProps {
  message: Message;
  // When true, the assistant message is actively streaming — show the typing
  // indicator until the first chunk arrives, plus a live "▍" caret.
  streaming?: boolean;
}

function formatTime(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function MessageRow({ message, streaming = false }: MessageRowProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  return (
    <div className="msg">
      <div className={`msg__avatar msg__avatar--${isUser ? "user" : "assistant"}`}>
        {isUser ? "You" : "A"}
      </div>
      <div className="msg__body">
        <div className="msg__role">{isUser ? "You" : "Atlas"}</div>
        {isUser ? (
          <div className="msg__content msg__content--user">{message.content}</div>
        ) : (
          <div className="msg__content">
            {message.content === "" && streaming ? (
              <TypingIndicator />
            ) : (
              <>
                <Markdown
                  content={message.content + (streaming ? "▍" : "")}
                />
                {streaming && (
                  <span className="spinner spinner--inline" aria-label="streaming" />
                )}
              </>
            )}
          </div>
        )}
        {isAssistant && !streaming && message.content !== "" && (
          <Citations content={message.content} citations={message.citations} />
        )}
        {message.created_at && (
          <div className="msg__time">{formatTime(message.created_at)}</div>
        )}
      </div>
    </div>
  );
}
