import { getGreeting } from "../../hooks/useAtlasActions";
import type { AtlasMessage } from "../../api/atlas";

interface AtlasHeroProps {
  onSuggestionClick: (prompt: string) => void;
}

const SUGGESTIONS = [
  { icon: "📄", label: "Summarize a meeting", prompt: "Summarize the key points from this meeting." },
  { icon: "🧠", label: "Explain a concept", prompt: "Explain the main concept discussed in the meeting." },
  { icon: "❓", label: "Generate a quiz", prompt: "Generate a quiz based on the meeting content." },
  { icon: "📌", label: "Find action items", prompt: "What are the action items from this meeting?" },
  { icon: "📚", label: "Review learning outputs", prompt: "Review the learning outputs from this meeting." },
  { icon: "📝", label: "Create study notes", prompt: "Create study notes from this meeting." },
];

export function AtlasHero({ onSuggestionClick }: AtlasHeroProps) {
  return (
    <div className="atlas-hero">
      <div className="atlas-hero-greeting">{getGreeting()}</div>
      <h1 className="atlas-hero-title">Atlas</h1>
      <div className="atlas-hero-subtitle">Meeting Intelligence Assistant</div>
      <p className="atlas-hero-desc">
        I'm Atlas, your Meeting Intelligence Assistant. I can help you understand
        meetings, explore learning material, generate quizzes, explain concepts, and
        answer questions.
      </p>
      <div className="atlas-suggestion-grid">
        {SUGGESTIONS.map((s) => (
          <button key={s.label} className="atlas-suggestion-card" onClick={() => onSuggestionClick(s.prompt)}>
            <span className="atlas-suggestion-icon">{s.icon}</span>
            <span className="atlas-suggestion-label">{s.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatMessages({ messages, isLoading }: { messages: AtlasMessage[]; isLoading: boolean }) {
  return (
    <div className="atlas-chat-messages">
      {messages.map((msg) => (
        <div key={msg.id} className={`atlas-message ${msg.role}`}>
          <div className="atlas-message-content">{msg.content}</div>
          <div className="atlas-message-time">{new Date(msg.created_at).toLocaleTimeString()}</div>
        </div>
      ))}
      {isLoading && (
        <div className="atlas-message assistant">
          <div className="atlas-message-typing">
            <span></span><span></span><span></span>
          </div>
        </div>
      )}
    </div>
  );
}

export function ChatInput({
  value,
  onChange,
  onSend,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="atlas-chat-input-area">
      <textarea
        className="atlas-chat-input"
        placeholder="Ask Atlas anything..."
        rows={2}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
      />
      <button className="atlas-chat-send" onClick={onSend} disabled={disabled || !value.trim()}>
        Send
      </button>
    </div>
  );
}

export function SuggestionCards({ onSelect }: { onSelect: (prompt: string) => void }) {
  const SUGGESTIONS = [
    { icon: "📄", label: "Summarize a meeting", prompt: "Summarize the key points from this meeting." },
    { icon: "🧠", label: "Explain a concept", prompt: "Explain the main concept discussed in the meeting." },
    { icon: "❓", label: "Generate a quiz", prompt: "Generate a quiz based on the meeting content." },
    { icon: "📌", label: "Find action items", prompt: "What are the action items from this meeting?" },
    { icon: "📚", label: "Review learning outputs", prompt: "Review the learning outputs from this meeting." },
    { icon: "📝", label: "Create study notes", prompt: "Create study notes from this meeting." },
  ];

  return (
    <div className="atlas-suggestion-grid">
      {SUGGESTIONS.map((s) => (
        <button key={s.label} className="atlas-suggestion-card" onClick={() => onSelect(s.prompt)}>
          <span className="atlas-suggestion-icon">{s.icon}</span>
          <span className="atlas-suggestion-label">{s.label}</span>
        </button>
      ))}
    </div>
  );
}

export function ChatWindow({
  messages,
  isLoading,
  inputValue,
  onInputChange,
  onSend,
  isEmpty,
  onSuggestionClick,
}: {
  messages: AtlasMessage[];
  isLoading: boolean;
  inputValue: string;
  onInputChange: (v: string) => void;
  onSend: () => void;
  isEmpty: boolean;
  onSuggestionClick: (prompt: string) => void;
}) {
  if (isEmpty) {
    return (
      <main className="atlas-chat">
        <AtlasHero onSuggestionClick={onSuggestionClick} />
        <ChatInput
          value={inputValue}
          onChange={onInputChange}
          onSend={onSend}
          disabled={isLoading}
        />
      </main>
    );
  }

  const safeMessages = messages.map((m) => ({
    ...m,
    created_at: m.created_at ?? new Date().toISOString(),
  }));

  return (
    <main className="atlas-chat">
      <ChatMessages messages={safeMessages} isLoading={isLoading} />
      <ChatInput
        value={inputValue}
        onChange={onInputChange}
        onSend={onSend}
        disabled={isLoading}
      />
    </main>
  );
}
