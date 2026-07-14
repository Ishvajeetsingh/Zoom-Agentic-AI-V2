import { useEffect, useRef, useState } from "react";
import type { Conversation } from "@/types";

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onOpenMenu?: () => void;
}

export function Sidebar({
  conversations,
  activeId,
  loading,
  onSelect,
  onCreate,
  onRename,
  onDelete,
  onOpenMenu,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar__header">
        <button
          type="button"
          className="sidebar__icon-btn sidebar__menu-btn"
          onClick={onOpenMenu}
          aria-label="Open sidebar"
        >
          ☰
        </button>
        <div className="sidebar__logo">
          <div className="sidebar__logo-mark">A</div>
          Atlas
        </div>
      </div>

      <button type="button" className="sidebar__new" onClick={onCreate}>
        ＋ New chat
      </button>

      <div className="sidebar__list">
        <div className="sidebar__group-label">Conversations</div>
        {loading && (
          <div style={{ padding: "10px 8px", color: "var(--fg-faint)", fontSize: 12 }}>
            <span className="spinner" style={{ width: 14, height: 14 }} /> Loading…
          </div>
        )}
        {!loading && conversations.length === 0 && (
          <div style={{ padding: "10px 8px", color: "var(--fg-faint)", fontSize: 12 }}>
            No conversations yet.
          </div>
        )}
        {conversations.map((c) => (
          <ConversationItem
            key={c.id}
            conversation={c}
            active={c.id === activeId}
            onSelect={() => onSelect(c.id)}
            onRename={(title) => onRename(c.id, title)}
            onDelete={() => onDelete(c.id)}
          />
        ))}
      </div>
    </aside>
  );
}

interface ConversationItemProps {
  conversation: Conversation;
  active: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
}

function ConversationItem({
  conversation,
  active,
  onSelect,
  onRename,
  onDelete,
}: ConversationItemProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conversation.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const commit = () => {
    const v = draft.trim();
    if (v && v !== conversation.title) onRename(v);
    else setDraft(conversation.title);
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="sidebar__item" style={{ padding: 4 }}>
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
              setDraft(conversation.title);
              setEditing(false);
            }
          }}
          autoFocus
        />
      </div>
    );
  }

  return (
    <div
      className={`sidebar__item${active ? " sidebar__item--active" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onSelect();
      }}
    >
      <span aria-hidden style={{ color: "var(--fg-faint)" }}>💬</span>
      <span className="sidebar__item-title">{conversation.title || "Untitled"}</span>
      <span className="sidebar__item-actions">
        <button
          type="button"
          className="sidebar__icon-btn"
          onClick={(e) => {
            e.stopPropagation();
            setDraft(conversation.title);
            setEditing(true);
          }}
          aria-label="Rename"
          title="Rename"
        >
          ✎
        </button>
        <button
          type="button"
          className="sidebar__icon-btn sidebar__icon-btn--danger"
          onClick={(e) => {
            e.stopPropagation();
            if (window.confirm(`Delete "${conversation.title}"?`)) onDelete();
          }}
          aria-label="Delete"
          title="Delete"
        >
          🗑
        </button>
      </span>
    </div>
  );
}
