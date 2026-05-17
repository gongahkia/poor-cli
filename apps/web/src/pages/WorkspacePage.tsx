import { ChangeEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, ClipboardList, FolderSearch, History, RotateCw } from "lucide-react";

import { useToast } from "@/components/notifications/ToastProvider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { addWatchlistItem, appendAuditEvent, listAuditEvents, listDossierRecords, loadWorkspaceStore, recordWatchlistCheck, saveWorkspaceStore } from "@/lib/workspace-store";
import type { WorkspaceAuditEventType } from "@/lib/workspace-store";
import { resolveActiveSession } from "@/lib/workspace";

const DEFAULT_WATCHLIST_MODULES = ["acra", "gebiz", "bca", "boa", "cea", "hsa", "hlb"];

export function WorkspacePage() {
  const [store, setStore] = useState(() => loadWorkspaceStore());
  const [query, setQuery] = useState("");
  const [folderId, setFolderId] = useState<string>("all");
  const [eventType, setEventType] = useState<WorkspaceAuditEventType | "all">("all");
  const [watchIdentifier, setWatchIdentifier] = useState("");
  const [channel, setChannel] = useState<"in_app" | "email" | "webhook">("in_app");
  const session = resolveActiveSession();
  const { notify } = useToast();

  const folders = store.folders.filter((folder) => folder.workspaceId === session.workspaceId);
  const dossiers = useMemo(() => listDossierRecords(store, session, {
    query,
    ...(folderId === "all" ? {} : { folderId }),
  }), [folderId, query, session, store]);
  const auditEvents = useMemo(() => listAuditEvents(
    store,
    session,
    eventType === "all" ? undefined : eventType,
  ), [eventType, session, store]);
  const watchlistItems = store.watchlistItems.filter((item) => item.workspaceId === session.workspaceId);
  const alerts = store.alerts.filter((alert) => alert.workspaceId === session.workspaceId);
  const bulkJobs = store.bulkJobs.filter((job) => job.workspaceId === session.workspaceId);

  const commitStore = (nextStore: typeof store) => {
    saveWorkspaceStore(nextStore);
    setStore(nextStore);
  };

  const handleAddWatch = () => {
    if (watchIdentifier.trim() === "") {
      notify({ title: "Identifier required", description: "Add a company name or UEN to watch.", tone: "error" });
      return;
    }
    const withItem = addWatchlistItem(store, session, {
      identifier: watchIdentifier.trim(),
      modules: DEFAULT_WATCHLIST_MODULES,
      notificationChannel: channel,
    });
    const audited = appendAuditEvent(withItem, session, {
      eventType: "watchlist_change",
      permission: "watchlist:manage",
      input: { identifier: watchIdentifier.trim(), modules: DEFAULT_WATCHLIST_MODULES },
      output: { status: "watching" },
      metadata: { notificationChannel: channel },
    });
    commitStore(audited);
    setWatchIdentifier("");
    notify({ title: "Watchlist updated", description: "Daily rerun metadata and alert history are now tracked.", tone: "success" });
  };

  const handleCheckNow = (itemId: string) => {
    const checked = recordWatchlistCheck(store, session, itemId);
    const audited = appendAuditEvent(checked, session, {
      eventType: "watchlist_change",
      permission: "watchlist:manage",
      input: { itemId },
      output: { status: "queued" },
      metadata: { trigger: "manual_check_now" },
    });
    commitStore(audited);
    notify({ title: "Watchlist check queued", tone: "info" });
  };

  return (
    <main className="min-h-dvh bg-background px-4 py-8 sm:px-6 sm:py-10">
      <section className="mx-auto w-full max-w-6xl space-y-6">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{session.workspaceName}</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-normal text-foreground">Workspace</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Persisted dossiers, watchlists, bulk jobs, and immutable audit events for this workspace.
            </p>
          </div>
          <Button asChild variant="outline">
            <Link to="/">Search</Link>
          </Button>
        </header>

        <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <FolderSearch className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold text-foreground">Dossier library</h2>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
            <Input
              aria-label="Search saved dossiers"
              onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)}
              placeholder="Search company name, UEN, or input"
              value={query}
            />
            <select
              aria-label="Filter by folder"
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
              onChange={(event) => setFolderId(event.target.value)}
              value={folderId}
            >
              <option value="all">All folders</option>
              {folders.map((folder) => (
                <option key={folder.id} value={folder.id}>{folder.name}</option>
              ))}
            </select>
          </div>
          <div className="mt-4 overflow-x-auto rounded-lg border border-border">
            <table className="min-w-[760px] w-full table-fixed text-left text-sm">
              <thead className="bg-muted text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="w-56 px-3 py-2">Entity</th>
                  <th className="w-32 px-3 py-2">UEN</th>
                  <th className="w-36 px-3 py-2">Folder</th>
                  <th className="w-44 px-3 py-2">Updated</th>
                  <th className="w-28 px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {dossiers.map((record) => (
                  <tr className="border-t border-border align-top" key={record.id}>
                    <td className="px-3 py-3">
                      <p className="truncate font-medium text-foreground">{record.entityName ?? record.identifier}</p>
                      <p className="truncate text-xs text-muted-foreground">{record.gaps.length} gaps; {record.provenance.length} sources</p>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">{record.uen ?? "-"}</td>
                    <td className="px-3 py-3">{folders.find((folder) => folder.id === record.folderId)?.name ?? "Inbox"}</td>
                    <td className="px-3 py-3 text-muted-foreground">{new Date(record.updatedAt).toLocaleString()}</td>
                    <td className="px-3 py-3">
                      <Link className="font-medium underline-offset-4 hover:underline" to={`/c/${encodeURIComponent(record.uen ?? record.identifier)}`}>
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
                {dossiers.length === 0 ? (
                  <tr>
                    <td className="px-3 py-6 text-sm text-muted-foreground" colSpan={5}>No saved dossiers match this workspace view.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,0.8fr)]">
          <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center gap-2">
              <Bell className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold text-foreground">Watchlists</h2>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_150px_auto]">
              <Input
                aria-label="Watchlist identifier"
                onChange={(event) => setWatchIdentifier(event.target.value)}
                placeholder="Company name or UEN"
                value={watchIdentifier}
              />
              <select
                aria-label="Notification channel"
                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                onChange={(event) => setChannel(event.target.value as typeof channel)}
                value={channel}
              >
                <option value="in_app">In-app</option>
                <option value="email">Email</option>
                <option value="webhook">Webhook</option>
              </select>
              <Button onClick={handleAddWatch} type="button">Watch</Button>
            </div>
            <div className="mt-4 space-y-3">
              {watchlistItems.map((item) => (
                <div className="rounded-md border border-border p-3" key={item.id}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-foreground">{item.label}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {item.modules.join(", ")} · next {new Date(item.nextRunAt).toLocaleString()}
                      </p>
                    </div>
                    <Button onClick={() => handleCheckNow(item.id)} size="sm" type="button" variant="outline">
                      <RotateCw className="mr-1 h-3.5 w-3.5" /> Check
                    </Button>
                  </div>
                </div>
              ))}
              {watchlistItems.length === 0 ? (
                <p className="text-sm text-muted-foreground">No watched counterparties yet.</p>
              ) : null}
            </div>
          </section>

          <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center gap-2">
              <ClipboardList className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold text-foreground">Bulk jobs</h2>
            </div>
            <div className="mt-4 space-y-3">
              {bulkJobs.slice(0, 5).map((job) => (
                <div className="rounded-md border border-border p-3" key={job.id}>
                  <p className="font-medium text-foreground">{job.status.replace("_", " ")}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {job.executedCount}/{job.requestedCount} rows · high {job.riskSummary.high} · gaps {job.riskSummary.gaps}
                  </p>
                </div>
              ))}
              {bulkJobs.length === 0 ? <p className="text-sm text-muted-foreground">Bulk runs will appear here after execution.</p> : null}
            </div>
          </section>
        </div>

        <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold text-foreground">Audit log</h2>
            </div>
            <select
              aria-label="Audit event type"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              onChange={(event) => setEventType(event.target.value as typeof eventType)}
              value={eventType}
            >
              <option value="all">All events</option>
              <option value="search">Search</option>
              <option value="dossier_generation">Dossier generation</option>
              <option value="memo_generation">Memo generation</option>
              <option value="export">Export</option>
              <option value="watchlist_change">Watchlist change</option>
              <option value="bulk_run">Bulk run</option>
            </select>
          </div>
          <div className="mt-4 overflow-x-auto rounded-lg border border-border">
            <table className="min-w-[840px] w-full table-fixed text-left text-sm">
              <thead className="bg-muted text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="w-44 px-3 py-2">Time</th>
                  <th className="w-40 px-3 py-2">Event</th>
                  <th className="w-32 px-3 py-2">Actor</th>
                  <th className="w-32 px-3 py-2">Input</th>
                  <th className="w-32 px-3 py-2">Output</th>
                  <th className="w-44 px-3 py-2">Sources</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.slice(0, 40).map((event) => (
                  <tr className="border-t border-border align-top" key={event.id}>
                    <td className="px-3 py-3 text-muted-foreground">{new Date(event.occurredAt).toLocaleString()}</td>
                    <td className="px-3 py-3">{event.eventType}</td>
                    <td className="px-3 py-3">{event.actorRole}</td>
                    <td className="px-3 py-3 font-mono text-xs">{event.inputFingerprint}</td>
                    <td className="px-3 py-3 font-mono text-xs">{event.outputHash}</td>
                    <td className="px-3 py-3">
                      <p className="line-clamp-2">{event.provenance.map((item) => item.source).join(", ") || "-"}</p>
                    </td>
                  </tr>
                ))}
                {auditEvents.length === 0 ? (
                  <tr>
                    <td className="px-3 py-6 text-sm text-muted-foreground" colSpan={6}>No audit events recorded yet.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        {alerts.length === 0 ? null : (
          <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
            <h2 className="text-base font-semibold text-foreground">Alert history</h2>
            <div className="mt-3 space-y-2">
              {alerts.slice(0, 8).map((alert) => (
                <p className="rounded-md border border-border p-3 text-sm text-muted-foreground" key={alert.id}>
                  <span className="font-medium text-foreground">{alert.title}</span> · {alert.message}
                </p>
              ))}
            </div>
          </section>
        )}
      </section>
    </main>
  );
}
