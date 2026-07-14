import { useEffect, useRef, useState } from "react";

interface ChatComposerProps {
  onSend: (text: string) => void;
  onStop?: () => void;
  streaming: boolean;
  disabled?: boolean;
}

export function ChatComposer({ onSend, onStop, streaming, disabled }: ChatComposerProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the textarea up to a max height.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || streaming || disabled) return;
    onSend(text);
    setValue("");
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="chat__composer">
      <div className="chat__composer-inner">
        <div className="chat__textarea-wrap">
          <textarea
            ref={ref}
            className="chat__textarea"
            placeholder="Message Atlas…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            disabled={disabled}
            aria-label="Message Atlas"
          />
        </div>
        {streaming ? (
          <button
            type="button"
            className="chat__send chat__send--stop"
            onClick={onStop}
            aria-label="Stop generating"
            title="Stop"
          >
            ■
          </button>
        ) : (
          <button
            type="button"
            className="chat__send"
            onClick={submit}
            disabled={disabled || value.trim().length === 0}
            aria-label="Send message"
            title="Send"
          >
            ↑
          </button>
        )}
      </div>
      <div className="chat__composer-hint">
        Atlas can make mistakes. Press Enter to send, Shift+Enter for a new line.
      </div>
    </div>
  );
}
