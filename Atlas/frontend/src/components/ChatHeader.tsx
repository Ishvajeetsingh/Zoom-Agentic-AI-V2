import { useEffect, useRef, useState } from "react";
import type { Conversation } from "@/types";

interface ChatHeaderProps {
  conversation: Conversation | null;
  onRename: (title: string) => void;
  onDelete: () => void;
  onOpenSidebar?: () => void;
}

export function ChatHeader({ conversation, onRename, onDelete, onOpenSidebar }: ChatHeaderProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conversation?.title ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setDraft(conversation?.title ?? "");
  }, [conversation?.id, conversation?.title]);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const commit = () => {
    const v = draft.trim();
    if (v && conversation && v !== conversation.title) onRename(v);
    else setDraft(conversation?.title ?? "");
    setEditing(false);
  };

  return (
    <header className="chat__header">
      {onOpenSidebar && (
        <button
          type="button"
          className="sidebar__icon-btn"
          onClick={onOpenSidebar}
          aria-label="Open menu"
          style={{ display: "grid" }}
        >
          ☰
        </button>
      )}
      {editing ? (
        <input
          ref={inputRef}
          className="chat__rename-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commit();
            } else if (e.key === "Escape") {
              setDraft(conversation?.title ?? "");
              setEditing(false);
            }
          }}
          autoFocus
        />
      ) : (
        <div
          className="chat__header-title"
          onClick={() => conversation && setEditing(true)}
          title={conversation ? "Click to rename" : ""}
          style={{ cursor: conversation ? "text" : "default" }}
        >
          {conversation?.title ?? "Atlas"}
        </div>
      )}
      <div className="chat__header-actions">
        {conversation && (
          <>
            <button
              type="button"
              className="sidebar__icon-btn"
              onClick={() => setEditing(true)}
              aria-label="Rename"
              title="Rename"
            >
              ✎
            </button>
            <button
              type="button"
              className="sidebar__icon-btn sidebar__icon-btn--danger"
              onClick={() => {
                if (window.confirm(`Delete "${conversation.title}"?`)) onDelete();
              }}
              aria-label="Delete"
              title="Delete"
            >
              🗑
            </button>
          </>
        )}
      </div>
    </header>
  );
}
