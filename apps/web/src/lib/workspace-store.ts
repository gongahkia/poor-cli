import type { AnalystMemoResponse } from "@/types/analyst-memo";
import type { BulkDossierResponse } from "@/types/bulk";
import type { BusinessDossier } from "@/types/dossier";
import type {
  CounterpartyResolutionCandidate,
  PeopleDiscovery,
  WebPresence,
} from "@/lib/api/client";
import { getAnalystFollowUps, formatAnalystFollowUpInputSummary, followUpPriorityLabel } from "@/lib/next-checks";
import type { ReportExportFormat, ReportWritingStyle } from "@/lib/report-template";
import type { CddOrchestrationTrace } from "@/types/orchestration";
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

export type CddCaseStatus =
  | "draft"
  | "in_review"
  | "needs_follow_up"
  | "ready_for_export"
  | "archived";

export type CddCaseNote = {
  id: string;
  body: string;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  updatedBy: string;
};

export type CddCaseFollowUpTask = {
  id: string;
  title: string;
  description: string | null;
  source: "analyst" | "dossier_analyst_follow_up" | "dossier_next_check" | "memo_next_step";
  sourceRef: string | null;
  status: "open" | "completed";
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  createdBy: string;
  updatedBy: string;
};

export type CddCaseExportRecord = {
  id: string;
  format: ReportExportFormat | "json";
  packageType: "report_package" | "case_json";
  filename: string;
  exportedAt: string;
  exportedBy: string;
  writingStyle?: ReportWritingStyle;
  statusAtExport: CddCaseStatus;
};

export type CddCaseAuditEventType =
  | "case_created"
  | "candidate_selected"
  | "dossier_attached"
  | "status_changed"
  | "note_added"
  | "task_added"
  | "task_completed"
  | "task_reopened"
  | "export_recorded"
  | "case_imported";

export type CddCaseAuditEvent = {
  id: string;
  version: 1;
  eventType: CddCaseAuditEventType;
  occurredAt: string;
  actorId: string;
  actorRole: WorkspaceSession["role"];
  summary: string;
  metadata: Record<string, unknown>;
};

export type CddCaseEvidencePack = {
  generatedAt: string | null;
  dossierTitle: string | null;
  summary: BusinessDossier["summary"];
  evidence: BusinessDossier["evidence"];
  records: BusinessDossier["records"] | null;
  provenance: BusinessDossier["provenance"];
  freshness: BusinessDossier["freshness"];
  gaps: BusinessDossier["gaps"];
  limits: BusinessDossier["limits"];
  sourceCoverage: NonNullable<BusinessDossier["sourceCoverage"]>;
  analystFollowUps: NonNullable<BusinessDossier["analystFollowUps"]>;
  webPresence?: WebPresence;
  peopleDiscovery?: PeopleDiscovery;
  orchestration?: CddOrchestrationTrace;
};

export type CddCaseRecord = {
  id: string;
  version: 1;
  workspaceId: string;
  storageScope: "browser_local";
  status: CddCaseStatus;
  counterpartyIdentifier: string;
  selectedCandidate: CounterpartyResolutionCandidate | null;
  candidateIdentifier: string | null;
  dossier?: BusinessDossier;
  memoState?: AnalystMemoResponse;
  evidencePack: CddCaseEvidencePack;
  analystNotes: CddCaseNote[];
  followUpTasks: CddCaseFollowUpTask[];
  exports: CddCaseExportRecord[];
  auditEvents: CddCaseAuditEvent[];
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  updatedBy: string;
};

export type CddCaseJsonPackage = {
  schemaVersion: "dude-cdd-case/v1";
  exportedAt: string;
  storageScope: "browser_local";
  limits: string[];
  case: CddCaseRecord;
};

export type WorkspaceAuditEventType =
  | "search"
  | "dossier_generation"
  | "dossier_update"
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
  cases: CddCaseRecord[];
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
  cases: [],
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
      cases: Array.isArray(parsed.cases) ? parsed.cases : [],
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

const emptyEvidencePack = (): CddCaseEvidencePack => ({
  generatedAt: null,
  dossierTitle: null,
  summary: [],
  evidence: [],
  records: null,
  provenance: [],
  freshness: [],
  gaps: [],
  limits: [],
  sourceCoverage: [],
  analystFollowUps: [],
});

const candidateIdentifier = (candidate: CounterpartyResolutionCandidate | null): string | null =>
  candidate === null ? null : candidate.uen ?? candidate.officialIdentifier ?? candidate.entityName;

export const buildCddCaseId = (
  session: Pick<WorkspaceSession, "workspaceId">,
  input: { counterpartyIdentifier: string },
): string => hashValue({
  counterpartyIdentifier: input.counterpartyIdentifier.trim().toLowerCase(),
  workspaceId: session.workspaceId,
});

const caseAuditEvent = (
  session: WorkspaceSession,
  input: {
    eventType: CddCaseAuditEventType;
    summary: string;
    metadata?: Record<string, unknown>;
    now?: string;
  },
): CddCaseAuditEvent => ({
  id: makeId("caseevt", input),
  version: 1,
  eventType: input.eventType,
  occurredAt: input.now ?? nowIso(),
  actorId: session.actorId,
  actorRole: session.role,
  summary: input.summary,
  metadata: input.metadata ?? {},
});

const buildEvidencePack = (input: {
  dossier: BusinessDossier;
  generatedAt?: string;
  orchestration?: CddOrchestrationTrace;
  peopleDiscovery?: PeopleDiscovery;
  webPresence?: WebPresence;
}): CddCaseEvidencePack => ({
  generatedAt: input.generatedAt ?? null,
  dossierTitle: input.dossier.title,
  summary: input.dossier.summary,
  evidence: input.dossier.evidence,
  records: input.dossier.records,
  provenance: input.dossier.provenance,
  freshness: input.dossier.freshness,
  gaps: input.dossier.gaps,
  limits: input.dossier.limits,
  sourceCoverage: input.dossier.sourceCoverage ?? [],
  analystFollowUps: getAnalystFollowUps(input.dossier),
  ...(input.webPresence === undefined ? {} : { webPresence: input.webPresence }),
  ...(input.peopleDiscovery === undefined ? {} : { peopleDiscovery: input.peopleDiscovery }),
  ...(input.orchestration === undefined ? {} : { orchestration: input.orchestration }),
});

const generatedFollowUpTasks = (
  caseId: string,
  session: WorkspaceSession,
  input: {
    dossier?: BusinessDossier;
    memoState?: AnalystMemoResponse;
    now: string;
  },
): CddCaseFollowUpTask[] => {
  const tasks: CddCaseFollowUpTask[] = [];

  if (input.dossier !== undefined) {
    const analystFollowUps = getAnalystFollowUps(input.dossier);
    analystFollowUps.forEach((followUp, index) => {
      const sourceRef = input.dossier?.analystFollowUps?.some((item) => item.id === followUp.id) === true
        ? `dossier.analystFollowUps.${index}`
        : `dossier.nextChecks.${index}`;
      tasks.push({
        id: hashValue({ caseId, sourceRef, followUpId: followUp.id, action: followUp.action }),
        title: `${followUpPriorityLabel(followUp.priority)}: ${followUp.action}`,
        description: [
          `Evidence gap: ${followUp.reason}`,
          `Why this matters: ${followUp.whyThisMatters}`,
          `Suggested input: ${formatAnalystFollowUpInputSummary(followUp)}`,
        ].join("\n"),
        source: input.dossier?.analystFollowUps?.some((item) => item.id === followUp.id) === true
          ? "dossier_analyst_follow_up"
          : "dossier_next_check",
        sourceRef,
        status: "open",
        createdAt: input.now,
        updatedAt: input.now,
        completedAt: null,
        createdBy: session.actorId,
        updatedBy: session.actorId,
      });
    });
  }

  if (input.memoState?.status === "ready") {
    input.memoState.decisionAid.nextSteps.forEach((step, index) => {
      const sourceRef = `memo.decisionAid.nextSteps.${index}`;
      tasks.push({
        id: hashValue({ caseId, sourceRef, step }),
        title: step,
        description: null,
        source: "memo_next_step",
        sourceRef,
        status: "open",
        createdAt: input.now,
        updatedAt: input.now,
        completedAt: null,
        createdBy: session.actorId,
        updatedBy: session.actorId,
      });
    });
  }

  return tasks;
};

const mergeFollowUpTasks = (
  existing: readonly CddCaseFollowUpTask[],
  incoming: readonly CddCaseFollowUpTask[],
): CddCaseFollowUpTask[] => {
  const existingById = new Map(existing.map((task) => [task.id, task]));
  const generated = incoming.map((task) => {
    const current = existingById.get(task.id);
    return current === undefined
      ? task
      : {
          ...task,
          status: current.status,
          completedAt: current.completedAt,
          createdAt: current.createdAt,
          createdBy: current.createdBy,
          updatedAt: current.updatedAt,
          updatedBy: current.updatedBy,
        };
  });
  const manual = existing.filter((task) => task.source === "analyst");
  return [...generated, ...manual].sort((left, right) => left.createdAt.localeCompare(right.createdAt));
};

const replaceCase = (store: WorkspaceStore, nextCase: CddCaseRecord): WorkspaceStore => ({
  ...store,
  cases: [
    nextCase,
    ...store.cases.filter((record) => !(record.id === nextCase.id && record.workspaceId === nextCase.workspaceId)),
  ],
});

export const getCddCase = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  caseId: string,
): CddCaseRecord | null => {
  assertWorkspaceAccess(session, "case:read");
  return store.cases.find((record) => record.id === caseId && record.workspaceId === session.workspaceId) ?? null;
};

export const listCddCases = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  options: { query?: string; status?: CddCaseStatus } = {},
): readonly CddCaseRecord[] => {
  assertWorkspaceAccess(session, "case:read");
  const query = options.query?.trim().toLowerCase() ?? "";
  return store.cases
    .filter((record) => record.workspaceId === session.workspaceId)
    .filter((record) => options.status === undefined || record.status === options.status)
    .filter((record) => {
      if (query === "") return true;
      return [
        record.counterpartyIdentifier,
        record.candidateIdentifier,
        record.selectedCandidate?.entityName,
        record.dossier?.title,
      ].filter((item): item is string => typeof item === "string")
        .some((item) => item.toLowerCase().includes(query));
    })
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
};

export const upsertCddCase = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  input: {
    counterpartyIdentifier: string;
    selectedCandidate?: CounterpartyResolutionCandidate | null;
    status?: CddCaseStatus;
    now?: string;
  },
): WorkspaceStore => {
  assertWorkspaceAccess(session, "case:write");
  const identifier = input.counterpartyIdentifier.trim();
  if (identifier === "") {
    throw new Error("Counterparty identifier is required.");
  }

  const at = input.now ?? nowIso();
  const caseId = buildCddCaseId(session, { counterpartyIdentifier: identifier });
  const existing = getCddCase(store, session, caseId);
  if (existing !== null) {
    const selectedCandidate = input.selectedCandidate === undefined ? existing.selectedCandidate : input.selectedCandidate;
    const selectedIdentifier = candidateIdentifier(selectedCandidate);
    const candidateChanged = selectedIdentifier !== existing.candidateIdentifier;
    return replaceCase(store, {
      ...existing,
      status: input.status ?? existing.status,
      counterpartyIdentifier: identifier,
      selectedCandidate,
      candidateIdentifier: selectedIdentifier,
      updatedAt: at,
      updatedBy: session.actorId,
      auditEvents: candidateChanged
        ? [
            caseAuditEvent(session, {
              eventType: "candidate_selected",
              summary: "Counterparty candidate selected for this CDD case.",
              metadata: { candidateIdentifier: selectedIdentifier },
              now: at,
            }),
            ...existing.auditEvents,
          ]
        : existing.auditEvents,
    });
  }

  const selectedCandidate = input.selectedCandidate ?? null;
  const record: CddCaseRecord = {
    id: caseId,
    version: 1,
    workspaceId: session.workspaceId,
    storageScope: "browser_local",
    status: input.status ?? "draft",
    counterpartyIdentifier: identifier,
    selectedCandidate,
    candidateIdentifier: candidateIdentifier(selectedCandidate),
    evidencePack: emptyEvidencePack(),
    analystNotes: [],
    followUpTasks: [],
    exports: [],
    auditEvents: [caseAuditEvent(session, {
      eventType: "case_created",
      summary: "CDD case created in browser-local workspace storage.",
      metadata: { counterpartyIdentifier: identifier, storageScope: "browser_local" },
      now: at,
    })],
    createdAt: at,
    updatedAt: at,
    createdBy: session.actorId,
    updatedBy: session.actorId,
  };

  return replaceCase(store, record);
};

export const attachDossierToCddCase = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  caseId: string,
  input: {
    dossier: BusinessDossier;
    memoState: AnalystMemoResponse;
    counterpartyIdentifier?: string;
    generatedAt?: string;
    orchestration?: CddOrchestrationTrace;
    peopleDiscovery?: PeopleDiscovery;
    selectedCandidate?: CounterpartyResolutionCandidate | null;
    webPresence?: WebPresence;
    now?: string;
  },
): WorkspaceStore => {
  assertWorkspaceAccess(session, "case:write");
  const existing = getCddCase(store, session, caseId);
  if (existing === null) {
    throw new Error(`CDD case ${caseId} was not found.`);
  }

  const at = input.now ?? nowIso();
  const selectedCandidate = input.selectedCandidate === undefined ? existing.selectedCandidate : input.selectedCandidate;
  const incomingTasks = generatedFollowUpTasks(caseId, session, {
    dossier: input.dossier,
    memoState: input.memoState,
    now: at,
  });
  const nextStatus = existing.status === "draft" ? "in_review" : existing.status;
  const nextCase: CddCaseRecord = {
    ...existing,
    status: nextStatus,
    counterpartyIdentifier: input.counterpartyIdentifier?.trim() || existing.counterpartyIdentifier,
    selectedCandidate,
    candidateIdentifier: candidateIdentifier(selectedCandidate),
    dossier: input.dossier,
    memoState: input.memoState,
    evidencePack: buildEvidencePack({
      dossier: input.dossier,
      ...(input.generatedAt === undefined ? {} : { generatedAt: input.generatedAt }),
      ...(input.orchestration === undefined ? {} : { orchestration: input.orchestration }),
      ...(input.peopleDiscovery === undefined ? {} : { peopleDiscovery: input.peopleDiscovery }),
      ...(input.webPresence === undefined ? {} : { webPresence: input.webPresence }),
    }),
    followUpTasks: mergeFollowUpTasks(existing.followUpTasks, incomingTasks),
    updatedAt: at,
    updatedBy: session.actorId,
    auditEvents: [
      caseAuditEvent(session, {
        eventType: "dossier_attached",
        summary: "CDD dossier and evidence pack attached to this case.",
        metadata: {
          dossierTitle: input.dossier.title,
          generatedAt: input.generatedAt ?? null,
          status: nextStatus,
        },
        now: at,
      }),
      ...existing.auditEvents,
    ],
  };
  return replaceCase(store, nextCase);
};

export const updateCddCaseStatus = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  caseId: string,
  status: CddCaseStatus,
  now = nowIso(),
): WorkspaceStore => {
  assertWorkspaceAccess(session, "case:write");
  const existing = getCddCase(store, session, caseId);
  if (existing === null || existing.status === status) return store;
  return replaceCase(store, {
    ...existing,
    status,
    updatedAt: now,
    updatedBy: session.actorId,
    auditEvents: [
      caseAuditEvent(session, {
        eventType: "status_changed",
        summary: "CDD case status changed.",
        metadata: { from: existing.status, to: status },
        now,
      }),
      ...existing.auditEvents,
    ],
  });
};

export const addCddCaseNote = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  caseId: string,
  body: string,
  now = nowIso(),
): WorkspaceStore => {
  assertWorkspaceAccess(session, "case:write");
  const existing = getCddCase(store, session, caseId);
  const trimmed = body.trim();
  if (existing === null || trimmed === "") return store;
  const note: CddCaseNote = {
    id: makeId("note", { caseId, body: trimmed, now }),
    body: trimmed,
    createdAt: now,
    updatedAt: now,
    createdBy: session.actorId,
    updatedBy: session.actorId,
  };
  return replaceCase(store, {
    ...existing,
    analystNotes: [note, ...existing.analystNotes],
    updatedAt: now,
    updatedBy: session.actorId,
    auditEvents: [
      caseAuditEvent(session, {
        eventType: "note_added",
        summary: "Analyst note added separately from source facts.",
        metadata: { noteId: note.id },
        now,
      }),
      ...existing.auditEvents,
    ],
  });
};

export const addCddCaseTask = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  caseId: string,
  input: { title: string; description?: string | null; now?: string },
): WorkspaceStore => {
  assertWorkspaceAccess(session, "case:write");
  const existing = getCddCase(store, session, caseId);
  const title = input.title.trim();
  if (existing === null || title === "") return store;
  const at = input.now ?? nowIso();
  const task: CddCaseFollowUpTask = {
    id: makeId("task", { caseId, title, at }),
    title,
    description: input.description?.trim() || null,
    source: "analyst",
    sourceRef: null,
    status: "open",
    createdAt: at,
    updatedAt: at,
    completedAt: null,
    createdBy: session.actorId,
    updatedBy: session.actorId,
  };
  return replaceCase(store, {
    ...existing,
    followUpTasks: [...existing.followUpTasks, task],
    updatedAt: at,
    updatedBy: session.actorId,
    auditEvents: [
      caseAuditEvent(session, {
        eventType: "task_added",
        summary: "Analyst follow-up task added.",
        metadata: { taskId: task.id },
        now: at,
      }),
      ...existing.auditEvents,
    ],
  });
};

export const setCddCaseTaskCompleted = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  caseId: string,
  taskId: string,
  completed: boolean,
  now = nowIso(),
): WorkspaceStore => {
  assertWorkspaceAccess(session, "case:write");
  const existing = getCddCase(store, session, caseId);
  if (existing === null) return store;

  let changed = false;
  const tasks = existing.followUpTasks.map((task) => {
    if (task.id !== taskId || task.status === (completed ? "completed" : "open")) {
      return task;
    }
    changed = true;
    return {
      ...task,
      status: completed ? "completed" as const : "open" as const,
      completedAt: completed ? now : null,
      updatedAt: now,
      updatedBy: session.actorId,
    };
  });
  if (!changed) return store;

  return replaceCase(store, {
    ...existing,
    followUpTasks: tasks,
    updatedAt: now,
    updatedBy: session.actorId,
    auditEvents: [
      caseAuditEvent(session, {
        eventType: completed ? "task_completed" : "task_reopened",
        summary: completed ? "CDD follow-up task completed." : "CDD follow-up task reopened.",
        metadata: { taskId },
        now,
      }),
      ...existing.auditEvents,
    ],
  });
};

export const recordCddCaseExport = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  caseId: string,
  input: {
    filename: string;
    format: CddCaseExportRecord["format"];
    packageType: CddCaseExportRecord["packageType"];
    writingStyle?: ReportWritingStyle;
    now?: string;
  },
): WorkspaceStore => {
  assertWorkspaceAccess(session, "export:run");
  const existing = getCddCase(store, session, caseId);
  if (existing === null) return store;
  const at = input.now ?? nowIso();
  const exportRecord: CddCaseExportRecord = {
    id: makeId("export", { caseId, filename: input.filename, at }),
    format: input.format,
    packageType: input.packageType,
    filename: input.filename,
    exportedAt: at,
    exportedBy: session.actorId,
    ...(input.writingStyle === undefined ? {} : { writingStyle: input.writingStyle }),
    statusAtExport: existing.status,
  };
  return replaceCase(store, {
    ...existing,
    exports: [exportRecord, ...existing.exports],
    updatedAt: at,
    updatedBy: session.actorId,
    auditEvents: [
      caseAuditEvent(session, {
        eventType: "export_recorded",
        summary: "Case export recorded for audit handoff.",
        metadata: {
          filename: input.filename,
          format: input.format,
          packageType: input.packageType,
          statusAtExport: existing.status,
        },
        now: at,
      }),
      ...existing.auditEvents,
    ],
  });
};

export const buildCddCaseJsonPackage = (
  record: CddCaseRecord,
  exportedAt = nowIso(),
): CddCaseJsonPackage => ({
  schemaVersion: "dude-cdd-case/v1",
  exportedAt,
  storageScope: "browser_local",
  limits: [
    "Case JSON is browser-local workflow state for analyst review.",
    "Analyst notes and follow-up tasks are user-authored workflow items, not source facts.",
    "Case status is workflow readiness only and does not imply approval, rejection, compliance clearance, or licensed advice.",
  ],
  case: record,
});

export const parseCddCaseJsonPackage = (text: string): CddCaseJsonPackage => {
  const parsed = JSON.parse(text) as Partial<CddCaseJsonPackage>;
  if (
    parsed.schemaVersion !== "dude-cdd-case/v1" ||
    parsed.storageScope !== "browser_local" ||
    parsed.case === undefined ||
    typeof parsed.case.id !== "string" ||
    typeof parsed.case.counterpartyIdentifier !== "string"
  ) {
    throw new Error("The selected file is not a Dude CDD case JSON package.");
  }
  return parsed as CddCaseJsonPackage;
};

export const importCddCaseJsonPackage = (
  store: WorkspaceStore,
  session: WorkspaceSession,
  input: { package: CddCaseJsonPackage; now?: string },
): WorkspaceStore => {
  assertWorkspaceAccess(session, "case:write");
  const at = input.now ?? nowIso();
  const incoming = input.package.case;
  const importedCase: CddCaseRecord = {
    ...incoming,
    version: 1,
    workspaceId: session.workspaceId,
    storageScope: "browser_local",
    evidencePack: {
      ...emptyEvidencePack(),
      ...(incoming.evidencePack ?? {}),
      analystFollowUps: incoming.evidencePack?.analystFollowUps ?? [],
    },
    analystNotes: Array.isArray(incoming.analystNotes) ? incoming.analystNotes : [],
    followUpTasks: Array.isArray(incoming.followUpTasks) ? incoming.followUpTasks : [],
    exports: Array.isArray(incoming.exports) ? incoming.exports : [],
    auditEvents: [
      caseAuditEvent(session, {
        eventType: "case_imported",
        summary: "CDD case imported from browser-local JSON package.",
        metadata: {
          originalWorkspaceId: incoming.workspaceId,
          importedPackageExportedAt: input.package.exportedAt,
        },
        now: at,
      }),
      ...(Array.isArray(incoming.auditEvents) ? incoming.auditEvents : []),
    ],
    updatedAt: at,
    updatedBy: session.actorId,
  };
  return replaceCase(store, importedCase);
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
