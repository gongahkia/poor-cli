import type { AnalystMemoResponse } from "@/types/analyst-memo";
import type { BulkDossierResponse } from "@/types/bulk";
import type { BusinessDossier } from "@/types/dossier";
import type { WebPresence } from "@/lib/api/client";
import {
  assertWorkspaceAccess,
  resolveActiveSession,
  type WorkspacePermission,
  type WorkspaceSession,
} from "@/lib/workspace";

export type WorkspaceFolder = {
  id: string;
  workspaceId: string;
  name: string;
  createdAt: string;
};

export type WorkspaceDossierRecord = {
  id: string;
  workspaceId: string;
  folderId: string;
  identifier: string;
  entityName: string | null;
  uen: string | null;
  title: string;
  dossier: BusinessDossier;
  analystMemo?: AnalystMemoResponse;
  webPresence?: WebPresence;
  provenance: BusinessDossier["provenance"];
  freshness: BusinessDossier["freshness"];
  gaps: BusinessDossier["gaps"];
  limits: BusinessDossier["limits"];
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  updatedBy: string;
};

export type WorkspaceAuditEventType =
  | "search"
  | "dossier_generation"
  | "memo_generation"
  | "export"
  | "watchlist_change"
  | "bulk_run";

export type WorkspaceAuditEvent = {
  id: string;
  version: 1;
  workspaceId: string;
  actorId: string;
  actorRole: WorkspaceSession["role"];
  eventType: WorkspaceAuditEventType;
  occurredAt: string;
  requestId: string;
  inputFingerprint: string;
  outputHash: string;
  inputSnapshot?: unknown;
  outputSnapshot?: unknown;
  provenance: BusinessDossier["provenance"];
  freshness: BusinessDossier["freshness"];
  metadata: Record<string, unknown>;
};

export type WorkspaceWatchlistItem = {
  id: string;
  workspaceId: string;
  identifier: string;
  label: string;
  modules: string[];
  notificationChannel: "in_app" | "email" | "webhook";
  createdAt: string;
  updatedAt: string;
  nextRunAt: string;
  createdBy: string;
};

export type WorkspaceAlert = {
  id: string;
  workspaceId: string;
  watchlistItemId: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  createdAt: string;
  acknowledgedAt: string | null;
};

export type WorkspaceBulkJob = {
  id: string;
  workspaceId: string;
  createdAt: string;
  createdBy: string;
  status: "completed" | "partial_failure" | "failed";
  requestedCount: number;
  executedCount: number;
  riskSummary: BulkRiskSummary;
  result: BulkDossierResponse;
};

export type BulkRiskSummary = {
  high: number;
  medium: number;
  low: number;
  none: number;
  gaps: number;
  upstreamFailures: number;
};

export type WorkspaceStore = {
  folders: WorkspaceFolder[];
  dossiers: WorkspaceDossierRecord[];
  auditEvents: WorkspaceAuditEvent[];
  watchlistItems: WorkspaceWatchlistItem[];
  alerts: WorkspaceAlert[];
  bulkJobs: WorkspaceBulkJob[];
};

const STORE_KEY = "dude.workspace.store.v1";
const DEFAULT_FOLDER_ID = "inbox";

const getBrowserStorage = (): Storage | null =>
  typeof window === "undefined" ? null : window.localStorage;

const nowIso = (): string => new Date().toISOString();

const makeId = (prefix: string, seed: unknown): string => {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : hashValue({ seed, at: nowIso() });
  return `${prefix}_${random}`;
};

const stableStringify = (value: unknown): string => {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`).join(",")}}`;
};

const snapshotAuditValue = (
  value: unknown,
  depth = 0,
  seen = new WeakSet<object>(),
): unknown => {
  if (value === null || typeof value === "number" || typeof value === "boolean") return value;
  if (typeof value === "string") {
    return value.length > 900 ? `${value.slice(0, 900)}... [truncated ${value.length - 900} chars]` : value;
  }
  if (typeof value === "undefined") return "[undefined]";
  if (typeof value === "function" || typeof value === "symbol" || typeof value === "bigint") {
    return `[${typeof value}]`;
  }
  if (depth >= 5) return "[truncated nested value]";

  if (typeof value === "object") {
    if (seen.has(value)) return "[circular]";
    seen.add(value);
  }

  if (Array.isArray(value)) {
    const maxItems = 8;
    const items = value.slice(0, maxItems).map((item) => snapshotAuditValue(item, depth + 1, seen));
    return value.length > maxItems
      ? [...items, { omittedItems: value.length - maxItems }]
      : items;
  }

  const record = value as Record<string, unknown>;
  const entries = Object.entries(record);
  const maxKeys = 24;
  const snapshot = Object.fromEntries(
    entries.slice(0, maxKeys).map(([key, entryValue]) => [
      key,
      snapshotAuditValue(entryValue, depth + 1, seen),
    ]),
  );
  if (entries.length > maxKeys) {
    snapshot["omittedKeys"] = entries.length - maxKeys;
  }
  return snapshot;
};

export const hashValue = (value: unknown): string => {
  const text = stableStringify(value);
  let hash = 5381;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) + hash) ^ text.charCodeAt(index);
  }
  return `h${(hash >>> 0).toString(16).padStart(8, "0")}`;
};

export const createWorkspaceStore = (workspaceId: string, createdAt = nowIso()): WorkspaceStore => ({
  folders: [{
    id: DEFAULT_FOLDER_ID,
    workspaceId,
    name: "Inbox",
    createdAt,
  }],
  dossiers: [],
  auditEvents: [],
  watchlistItems: [],
  alerts: [],
  bulkJobs: [],
});

export const loadWorkspaceStore = (storage: Storage | null = getBrowserStorage()): WorkspaceStore => {
  const session = resolveActiveSession();
  if (storage === null) return createWorkspaceStore(session.workspaceId);
  const raw = storage.getItem(STORE_KEY);
  if (raw === null) {
    const store = createWorkspaceStore(session.workspaceId);
    storage.setItem(STORE_KEY, JSON.stringify(store));
    return store;
  }
  try {
    const parsed = JSON.parse(raw) as WorkspaceStore;
    return {
      folders: Array.isArray(parsed.folders) ? parsed.folders : [],
      dossiers: Array.isArray(parsed.dossiers) ? parsed.dossiers : [],
      auditEvents: Array.isArray(parsed.auditEvents) ? parsed.auditEvents : [],
      watchlistItems: Array.isArray(parsed.watchlistItems) ? parsed.watchlistItems : [],
      alerts: Array.isArray(parsed.alerts) ? parsed.alerts : [],
      bulkJobs: Array.isArray(parsed.bulkJobs) ? parsed.bulkJobs : [],
    };
  } catch {
    const store = createWorkspaceStore(session.workspaceId);
    storage.setItem(STORE_KEY, JSON.stringify(store));
    return store;
  }
};

export const saveWorkspaceStore = (
  store: WorkspaceStore,
  storage: Storage | null = getBrowserStorage(),
): void => {
  storage?.setItem(STORE_KEY, JSON.stringify(store));
};

const summaryString = (dossier: BusinessDossier, label: string): string | null => {
  const value = dossier.summary.find((item) => item.label.toLowerCase() === label.toLowerCase())?.value;
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
};

export const upsertDossierRecord = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  input: {
    identifier: string;
    dossier: BusinessDossier;
    analystMemo?: AnalystMemoResponse;
    webPresence?: WebPresence;
    folderId?: string;
    now?: string;
  },
): WorkspaceStore => {
  assertWorkspaceAccess(session, "dossier:write");
  const at = input.now ?? nowIso();
  const entityName = summaryString(input.dossier, "Entity");
  const uen = summaryString(input.dossier, "UEN");
  const recordId = hashValue({ workspaceId: session.workspaceId, identifier: uen ?? entityName ?? input.identifier });
  const folderId = input.folderId ?? DEFAULT_FOLDER_ID;
  const existing = store.dossiers.find((record) => record.id === recordId && record.workspaceId === session.workspaceId);
  const nextRecord: WorkspaceDossierRecord = {
    id: recordId,
    workspaceId: session.workspaceId,
    folderId,
    identifier: input.identifier,
    entityName,
    uen,
    title: input.dossier.title,
    dossier: input.dossier,
    ...(input.analystMemo === undefined ? {} : { analystMemo: input.analystMemo }),
    ...(input.webPresence === undefined ? {} : { webPresence: input.webPresence }),
    provenance: input.dossier.provenance,
    freshness: input.dossier.freshness,
    gaps: input.dossier.gaps,
    limits: input.dossier.limits,
    createdAt: existing?.createdAt ?? at,
    updatedAt: at,
    createdBy: existing?.createdBy ?? session.actorId,
    updatedBy: session.actorId,
  };
  return {
    ...store,
    dossiers: [
      nextRecord,
      ...store.dossiers.filter((record) => !(record.id === recordId && record.workspaceId === session.workspaceId)),
    ],
  };
};

export const listDossierRecords = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  options: { query?: string; folderId?: string } = {},
): readonly WorkspaceDossierRecord[] => {
  assertWorkspaceAccess(session, "dossier:read");
  const query = options.query?.trim().toLowerCase() ?? "";
  return store.dossiers
    .filter((record) => record.workspaceId === session.workspaceId)
    .filter((record) => options.folderId === undefined || record.folderId === options.folderId)
    .filter((record) => {
      if (query === "") return true;
      return [record.identifier, record.entityName, record.uen]
        .filter((item): item is string => typeof item === "string")
        .some((item) => item.toLowerCase().includes(query));
    })
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
};

export const appendAuditEvent = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  input: {
    eventType: WorkspaceAuditEventType;
    permission?: WorkspacePermission;
    requestId?: string;
    input: unknown;
    output: unknown;
    provenance?: BusinessDossier["provenance"];
    freshness?: BusinessDossier["freshness"];
    metadata?: Record<string, unknown>;
    now?: string;
  },
): WorkspaceStore => {
  assertWorkspaceAccess(session, input.permission ?? "audit:read");
  const event: WorkspaceAuditEvent = {
    id: makeId("audit", input),
    version: 1,
    workspaceId: session.workspaceId,
    actorId: session.actorId,
    actorRole: session.role,
    eventType: input.eventType,
    occurredAt: input.now ?? nowIso(),
    requestId: input.requestId ?? makeId("req", input.input),
    inputFingerprint: hashValue(input.input),
    outputHash: hashValue(input.output),
    inputSnapshot: snapshotAuditValue(input.input),
    outputSnapshot: snapshotAuditValue(input.output),
    provenance: input.provenance ?? [],
    freshness: input.freshness ?? [],
    metadata: input.metadata ?? {},
  };
  return {
    ...store,
    auditEvents: [event, ...store.auditEvents],
  };
};

export const listAuditEvents = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  eventType?: WorkspaceAuditEventType,
): readonly WorkspaceAuditEvent[] => {
  assertWorkspaceAccess(session, "audit:read");
  return store.auditEvents
    .filter((event) => event.workspaceId === session.workspaceId)
    .filter((event) => eventType === undefined || event.eventType === eventType)
    .sort((left, right) => right.occurredAt.localeCompare(left.occurredAt));
};

export const summarizeBulkRisk = (result: BulkDossierResponse): BulkRiskSummary =>
  result.rows.reduce<BulkRiskSummary>((summary, row) => ({
    high: summary.high + (row.risk === "high" ? 1 : 0),
    medium: summary.medium + (row.risk === "medium" ? 1 : 0),
    low: summary.low + (row.risk === "low" ? 1 : 0),
    none: summary.none + (row.risk === "none" ? 1 : 0),
    gaps: summary.gaps + row.gapCodes.length,
    upstreamFailures: summary.upstreamFailures + (row.upstreamFailure ? 1 : 0),
  }), { high: 0, medium: 0, low: 0, none: 0, gaps: 0, upstreamFailures: 0 });

export const appendBulkJob = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  result: BulkDossierResponse,
  now = nowIso(),
): WorkspaceStore => {
  assertWorkspaceAccess(session, "bulk:run");
  const riskSummary = summarizeBulkRisk(result);
  const status: WorkspaceBulkJob["status"] = result.rows.every((row) => row.status === "error")
    ? "failed"
    : result.rows.some((row) => row.status === "error" || row.upstreamFailure || result.parseErrors.length > 0)
      ? "partial_failure"
      : "completed";
  return {
    ...store,
    bulkJobs: [{
      id: makeId("bulk", result),
      workspaceId: session.workspaceId,
      createdAt: now,
      createdBy: session.actorId,
      status,
      requestedCount: result.requestedCount,
      executedCount: result.executedCount,
      riskSummary,
      result,
    }, ...store.bulkJobs],
  };
};

const oneDayFrom = (at: string): string => new Date(new Date(at).getTime() + 24 * 60 * 60 * 1000).toISOString();

export const addWatchlistItem = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  input: {
    identifier: string;
    label?: string;
    modules: string[];
    notificationChannel: WorkspaceWatchlistItem["notificationChannel"];
    now?: string;
  },
): WorkspaceStore => {
  assertWorkspaceAccess(session, "watchlist:manage");
  const at = input.now ?? nowIso();
  const item: WorkspaceWatchlistItem = {
    id: hashValue({ workspaceId: session.workspaceId, identifier: input.identifier }),
    workspaceId: session.workspaceId,
    identifier: input.identifier,
    label: input.label?.trim() || input.identifier,
    modules: Array.from(new Set(input.modules)),
    notificationChannel: input.notificationChannel,
    createdAt: at,
    updatedAt: at,
    nextRunAt: oneDayFrom(at),
    createdBy: session.actorId,
  };
  return {
    ...store,
    watchlistItems: [
      item,
      ...store.watchlistItems.filter((existing) => !(existing.id === item.id && existing.workspaceId === session.workspaceId)),
    ],
  };
};

export const recordWatchlistCheck = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  itemId: string,
  now = nowIso(),
): WorkspaceStore => {
  assertWorkspaceAccess(session, "watchlist:manage");
  const item = store.watchlistItems.find((candidate) => candidate.id === itemId && candidate.workspaceId === session.workspaceId);
  if (item === undefined) return store;
  const nextItem = { ...item, updatedAt: now, nextRunAt: oneDayFrom(now) };
  const alert: WorkspaceAlert = {
    id: makeId("alert", { itemId, now }),
    workspaceId: session.workspaceId,
    watchlistItemId: item.id,
    severity: "info",
    title: "Watchlist check queued",
    message: `${item.label} will rerun ${item.modules.join(", ")} checks. Evidence changes create alert records here.`,
    createdAt: now,
    acknowledgedAt: null,
  };
  return {
    ...store,
    watchlistItems: store.watchlistItems.map((candidate) => candidate.id === item.id ? nextItem : candidate),
    alerts: [alert, ...store.alerts],
  };
};

export const persistDossierRecord = (input: Parameters<typeof upsertDossierRecord>[2]): void => {
  const session = resolveActiveSession();
  const store = loadWorkspaceStore();
  saveWorkspaceStore(upsertDossierRecord(store, session, input));
};

export const persistAuditEvent = (input: Parameters<typeof appendAuditEvent>[2]): void => {
  const session = resolveActiveSession();
  const store = loadWorkspaceStore();
  saveWorkspaceStore(appendAuditEvent(store, session, input));
};

export const persistBulkJob = (result: BulkDossierResponse): void => {
  const session = resolveActiveSession();
  const store = loadWorkspaceStore();
  const withJob = appendBulkJob(store, session, result);
  saveWorkspaceStore(appendAuditEvent(withJob, session, {
    eventType: "bulk_run",
    permission: "bulk:run",
    input: { requestedCount: result.requestedCount },
    output: result,
    metadata: { executedCount: result.executedCount, parseErrors: result.parseErrors.length },
  }));
};
