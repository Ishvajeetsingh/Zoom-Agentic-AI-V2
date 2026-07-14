interface EmptyStateProps {
  onCreate?: () => void;
}

export function EmptyState({ onCreate }: EmptyStateProps) {
  return (
    <div className="chat__empty">
      <div className="chat__empty-card">
        <div className="sidebar__logo-mark" style={{ margin: "0 auto 14px", width: 48, height: 48, fontSize: 22 }}>
          A
        </div>
        <div className="chat__empty-title">Atlas</div>
        <div className="chat__empty-sub">
          Ask anything. Atlas streams answers in real time and cites sources
          inline.
        </div>
        {onCreate && (
          <button
            type="button"
            className="sidebar__new"
            style={{ marginTop: 18, width: "100%" }}
            onClick={onCreate}
          >
            ＋ Start a new chat
          </button>
        )}
      </div>
    </div>
  );
}
