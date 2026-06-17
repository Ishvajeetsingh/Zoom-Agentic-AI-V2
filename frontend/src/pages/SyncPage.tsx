import { useEffect, useState, useCallback } from "react";
import {
  RefreshCw,
  Play,
  Activity,
  Clock,
  CheckCircle2,
  XCircle,
  Zap,
} from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";
import { getEnabledZoomAccounts } from "../api/zoomAccounts";
import {
  getSyncConfig,
  updateSyncConfig,
  syncNow,
  syncAllEnabled,
  getSyncHistory,
} from "../api/sync";
import type {
  ZoomAccount,
  SyncConfig,
  SyncHistoryEntry,
  SyncConfigUpdateRequest,
} from "../types/api";

function SyncStatusBadge({ status }: { status: string }) {
  if (status === "completed")
    return (
      <span className="status-badge status-completed">
        <span className="status-badge-dot" /> Completed
      </span>
    );
  if (status === "failed")
    return (
      <span className="status-badge status-failed">
        <span className="status-badge-dot" /> Failed
      </span>
    );
  if (status === "running")
    return (
      <span className="status-badge status-in-progress">
        <span className="status-badge-dot" /> Running
      </span>
    );
  return (
    <span className="status-badge status-pending">
      <span className="status-badge-dot" /> {status}
    </span>
  );
}

function AccountSyncRow({
  account,
  config,
  onSync,
  onConfigChange,
  syncing,
}: {
  account: ZoomAccount;
  config: SyncConfig | null;
  onSync: (id: string) => void;
  onConfigChange: (id: string, data: SyncConfigUpdateRequest) => void;
  syncing: boolean;
}) {
  const [localInterval, setLocalInterval] = useState(config?.sync_interval_minutes ?? 60);
  const [localLookback, setLocalLookback] = useState(config?.lookback_days ?? 30);
  const [localAutoProcess, setLocalAutoProcess] = useState(config?.auto_process ?? true);

  useEffect(() => {
    if (config) {
      setLocalInterval(config.sync_interval_minutes);
      setLocalLookback(config.lookback_days);
      setLocalAutoProcess(config.auto_process);
    }
  }, [config]);

  const handleToggleAutoSync = () => {
    const newVal = !(config?.auto_sync_enabled ?? false);
    onConfigChange(account.id, {
      auto_sync_enabled: newVal,
      sync_interval_minutes: localInterval,
      lookback_days: localLookback,
      auto_process: localAutoProcess,
    });
  };

  const handleSaveConfig = () => {
    onConfigChange(account.id, {
      auto_sync_enabled: config?.auto_sync_enabled ?? false,
      sync_interval_minutes: localInterval,
      lookback_days: localLookback,
      auto_process: localAutoProcess,
    });
  };

  return (
    <div className="panel" style={{ marginBottom: 16, padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 16 }}>
            {account.account_name}
            {account.is_default && (
              <span style={{ marginLeft: 8, fontSize: 12, color: "var(--color-warning)" }}>Default</span>
            )}
          </h3>
          <span style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>{account.zoom_account_id}</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => handleToggleAutoSync()}
          >
            {config?.auto_sync_enabled ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
            {config?.auto_sync_enabled ? "Auto Sync On" : "Auto Sync Off"}
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => onSync(account.id)}
            disabled={syncing}
          >
            <Play size={14} /> Sync Now
          </button>
        </div>
      </div>

      {config?.auto_sync_enabled && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label" style={{ fontSize: 12 }}>Interval (min)</label>
            <input
              className="form-input"
              type="number"
              min={5}
              max={1440}
              value={localInterval}
              onChange={(e) => setLocalInterval(Number(e.target.value))}
            />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label" style={{ fontSize: 12 }}>Lookback (days)</label>
            <input
              className="form-input"
              type="number"
              min={1}
              max={365}
              value={localLookback}
              onChange={(e) => setLocalLookback(Number(e.target.value))}
            />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-checkbox-label" style={{ fontSize: 12 }}>
              <input
                type="checkbox"
                checked={localAutoProcess}
                onChange={(e) => setLocalAutoProcess(e.target.checked)}
              /> Auto Process
            </label>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={handleSaveConfig}>Save</button>
        </div>
      )}

      {config?.last_sync_status && (
        <div style={{ marginTop: 12, fontSize: 13, color: "var(--color-text-secondary)" }}>
          Last sync: {config.last_sync_at ? new Date(config.last_sync_at).toLocaleString() : "\u2014"}
          {" \u00b7 "}<SyncStatusBadge status={config.last_sync_status} />
          {config.last_sync_error && (
            <div style={{ color: "var(--color-error)", marginTop: 4 }}>{config.last_sync_error}</div>
          )}
        </div>
      )}
    </div>
  );
}

export function SyncPage() {
  const [accounts, setAccounts] = useState<ZoomAccount[]>([]);
  const [configs, setConfigs] = useState<Record<string, SyncConfig>>({});
  const [history, setHistory] = useState<SyncHistoryEntry[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const accRes = await getEnabledZoomAccounts();
      setAccounts(accRes.items);

      const configMap: Record<string, SyncConfig> = {};
      for (const acc of accRes.items) {
        try {
          const cfg = await getSyncConfig(acc.id);
          configMap[acc.id] = cfg;
        } catch { /* config will be created on first access */ }
      }
      setConfigs(configMap);

      const histRes = await getSyncHistory({ limit: 20 });
      setHistory(histRes.items);
      setHistoryTotal(histRes.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sync data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSyncNow = async (accountId: string) => {
    try {
      setSyncing(true);
      setSyncMessage(null);
      const res = await syncNow(accountId);
      setSyncMessage(res.message);
      loadData();
    } catch (err) {
      setSyncMessage(`Sync failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSyncing(false);
    }
  };

  const handleSyncAll = async () => {
    try {
      setSyncing(true);
      setSyncMessage(null);
      const res = await syncAllEnabled();
      setSyncMessage(res.message);
      loadData();
    } catch (err) {
      setSyncMessage(`Sync failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSyncing(false);
    }
  };

  const handleConfigChange = async (accountId: string, data: SyncConfigUpdateRequest) => {
    try {
      const cfg = await updateSyncConfig(accountId, data);
      setConfigs((prev) => ({ ...prev, [accountId]: cfg }));
    } catch (err) {
      setSyncMessage(`Config update failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  return (
    <AppShell>
      <div className="page-container">
        <div className="page-header">
          <h1>Auto Sync</h1>
          <p className="page-header-subtitle">
            Configure automatic meeting discovery and processing for Zoom accounts
          </p>
        </div>

        <div className="page-header-actions">
          <button
            className="btn btn-primary"
            onClick={handleSyncAll}
            disabled={syncing}
          >
            <Zap size={16} /> Sync All Enabled
          </button>
          <button className="btn btn-secondary" onClick={loadData}>
            <RefreshCw size={16} /> Refresh
          </button>
        </div>

        {syncMessage && (
          <div className={`alert ${syncMessage.startsWith("Sync failed") ? "alert-error" : "alert-success"}`} style={{ marginBottom: 16 }}>
            {syncMessage}
          </div>
        )}

        {loading && <LoadingState message="Loading sync configuration..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error && (
          accounts.length > 0 ? (
            <>
              {accounts.map((acc) => (
                <AccountSyncRow
                  key={acc.id}
                  account={acc}
                  config={configs[acc.id] ?? null}
                  onSync={handleSyncNow}
                  onConfigChange={handleConfigChange}
                  syncing={syncing}
                />
              ))}

              <section className="panel" style={{ marginTop: 32 }}>
                <h2 style={{ fontSize: 16, marginBottom: 16 }}>Sync History ({historyTotal})</h2>
                {history.length > 0 ? (
                  <div style={{ overflowX: "auto" }}>
                    <table className="meeting-table">
                      <thead>
                        <tr>
                          <th>Account</th>
                          <th>Type</th>
                          <th>Status</th>
                          <th>Meetings</th>
                          <th>Transcripts</th>
                          <th>Queued</th>
                          <th>Duration</th>
                          <th>Started</th>
                        </tr>
                      </thead>
                      <tbody>
                        {history.map((h) => {
                          const acc = accounts.find((a) => a.id === h.zoom_account_id);
                          return (
                            <tr key={h.id}>
                              <td>{acc?.account_name ?? h.zoom_account_id.slice(0, 8)}</td>
                              <td>{h.sync_type}</td>
                              <td><SyncStatusBadge status={h.status} /></td>
                              <td className="cell-number">{h.meetings_discovered}</td>
                              <td className="cell-number">{h.transcripts_discovered}</td>
                              <td className="cell-number">{h.transcripts_queued}</td>
                              <td className="cell-number">
                                {h.duration_seconds != null ? `${h.duration_seconds.toFixed(1)}s` : "\u2014"}
                              </td>
                              <td className="cell-date">
                                {new Date(h.started_at).toLocaleString()}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState title="No Sync History" message="No sync operations have been run yet." />
                )}
              </section>
            </>
          ) : (
            <EmptyState
              title="No Enabled Zoom Accounts"
              message="Add and enable a Zoom account before configuring auto sync."
            />
          )
        )}
      </div>
    </AppShell>
  );
}
