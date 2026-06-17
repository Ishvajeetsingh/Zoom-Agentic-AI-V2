import { useEffect, useState, useCallback } from "react";
import {
  Plus,
  Trash2,
  Star,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Settings2,
} from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";
import {
  getZoomAccounts,
  createZoomAccount,
  updateZoomAccount,
  deleteZoomAccount,
  setDefaultZoomAccount,
} from "../api/zoomAccounts";
import type { ZoomAccount, ZoomAccountCreateRequest } from "../types/api";

function AccountModal({
  open,
  onClose,
  onSave,
  initial,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (data: ZoomAccountCreateRequest) => void;
  initial?: ZoomAccount | null;
}) {
  const [name, setName] = useState(initial?.account_name ?? "");
  const [zoomAccountId, setZoomAccountId] = useState(initial?.zoom_account_id ?? "");
  const [clientId, setClientId] = useState(initial?.client_id ?? "");
  const [clientSecret, setClientSecret] = useState("");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? false);

  useEffect(() => {
    if (open) {
      setName(initial?.account_name ?? "");
      setZoomAccountId(initial?.zoom_account_id ?? "");
      setClientId(initial?.client_id ?? "");
      setClientSecret("");
      setEnabled(initial?.enabled ?? true);
      setIsDefault(initial?.is_default ?? false);
    }
  }, [open, initial]);

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      account_name: name,
      zoom_account_id: zoomAccountId,
      client_id: clientId,
      client_secret: clientSecret || (initial ? "__keep__" : ""),
      enabled,
      is_default: isDefault,
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{initial ? "Edit Zoom Account" : "Add Zoom Account"}</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label className="form-label">Account Name</label>
              <input className="form-input" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="form-group">
              <label className="form-label">Zoom Account ID</label>
              <input className="form-input" value={zoomAccountId} onChange={(e) => setZoomAccountId(e.target.value)} required />
            </div>
            <div className="form-group">
              <label className="form-label">Client ID</label>
              <input className="form-input" value={clientId} onChange={(e) => setClientId(e.target.value)} required />
            </div>
            <div className="form-group">
              <label className="form-label">Client Secret{initial ? " (leave blank to keep current)" : ""}</label>
              <input className="form-input" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} required={!initial} />
            </div>
            <div className="form-group" style={{ display: "flex", gap: 20 }}>
              <label className="form-checkbox-label">
                <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Enabled
              </label>
              <label className="form-checkbox-label">
                <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} /> Default
              </label>
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary">{initial ? "Update" : "Create"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function ZoomAccountsPage() {
  const [accounts, setAccounts] = useState<ZoomAccount[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<ZoomAccount | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadAccounts = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await getZoomAccounts();
      setAccounts(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load accounts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  const handleCreate = async (data: ZoomAccountCreateRequest) => {
    try {
      setActionError(null);
      if (data.client_secret === "__keep__") {
        const { client_secret: _, ...updateData } = data;
        await updateZoomAccount(editingAccount!.id, updateData);
      } else if (editingAccount) {
        await updateZoomAccount(editingAccount!.id, data);
      } else {
        await createZoomAccount(data);
      }
      setModalOpen(false);
      setEditingAccount(null);
      loadAccounts();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to save account");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this Zoom account?")) return;
    try {
      setActionError(null);
      await deleteZoomAccount(id);
      loadAccounts();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete account");
    }
  };

  const handleSetDefault = async (id: string) => {
    try {
      setActionError(null);
      await setDefaultZoomAccount(id);
      loadAccounts();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to set default");
    }
  };

  return (
    <AppShell>
      <div className="page-container">
        <div className="page-header">
          <h1>Zoom Accounts</h1>
          <p className="page-header-subtitle">
            Manage multiple Zoom account connections ({total} account{total !== 1 ? "s" : ""})
          </p>
        </div>

        <div className="page-header-actions">
          <button
            className="btn btn-primary"
            onClick={() => { setEditingAccount(null); setModalOpen(true); }}
          >
            <Plus size={16} /> Add Account
          </button>
          <button className="btn btn-secondary" onClick={loadAccounts}>
            <RefreshCw size={16} /> Refresh
          </button>
        </div>

        {actionError && (
          <div className="alert alert-error" style={{ marginBottom: 16 }}>{actionError}</div>
        )}

        {loading && <LoadingState message="Loading accounts..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error && (
          accounts.length > 0 ? (
            <section className="panel">
              <div style={{ overflowX: "auto" }}>
                <table className="meeting-table">
                  <thead>
                    <tr>
                      <th>Account Name</th>
                      <th>Zoom Account ID</th>
                      <th>Status</th>
                      <th>Default</th>
                      <th>Last Sync</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accounts.map((a) => (
                      <tr key={a.id}>
                        <td className="cell-filename">{a.account_name}</td>
                        <td className="cell-number" style={{ fontFamily: "monospace", fontSize: 13 }}>
                          {a.zoom_account_id}
                        </td>
                        <td>
                          {a.enabled ? (
                            <span className="status-badge status-completed">
                              <span className="status-badge-dot" /> Enabled
                            </span>
                          ) : (
                            <span className="status-badge status-failed">
                              <span className="status-badge-dot" /> Disabled
                            </span>
                          )}
                        </td>
                        <td>
                          {a.is_default ? (
                            <Star size={16} style={{ color: "var(--color-warning)", fill: "currentColor" }} />
                          ) : (
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={() => handleSetDefault(a.id)}
                              title="Set as default"
                            >
                              <Star size={16} />
                            </button>
                          )}
                        </td>
                        <td className="cell-date">
                          {a.last_sync_at
                            ? new Date(a.last_sync_at).toLocaleString()
                            : "\u2014"}
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: 4 }}>
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={() => { setEditingAccount(a); setModalOpen(true); }}
                              title="Edit"
                            >
                              <Settings2 size={16} />
                            </button>
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={() => handleDelete(a.id)}
                              title="Delete"
                              style={{ color: "var(--color-error)" }}
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <EmptyState
              title="No Zoom Accounts"
              message="Add a Zoom account to enable multi-account meeting discovery and processing."
            />
          )
        )}

        <AccountModal
          open={modalOpen}
          onClose={() => { setModalOpen(false); setEditingAccount(null); }}
          onSave={handleCreate}
          initial={editingAccount}
        />
      </div>
    </AppShell>
  );
}
