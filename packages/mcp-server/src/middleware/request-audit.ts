import type { ToolErrorPayload } from "@dude/shared";

export type ToolInvocationStatus = "success" | "error";

export type ToolInvocationAuditRecord = {
  readonly traceId: string;
  readonly requestId: string;
  readonly tool: string;
  readonly status: ToolInvocationStatus;
  readonly startedAt: string;
  readonly finishedAt: string;
  readonly durationMs: number;
  readonly error?: Readonly<{
    readonly code: string;
    readonly source: string;
    readonly message: string;
    readonly retryable: boolean;
    readonly statusCode?: number;
    readonly category?: string;
    readonly severity?: "high" | "medium" | "low";
    readonly suggestedAction?: string;
  }>;
};

const DEFAULT_MAX_AUDIT_ENTRIES = 5000;
const MAX_AUDIT_ENTRIES_HARD_CAP = 50000;
const MIN_AUDIT_ENTRIES = 100;
const DEFAULT_AUDIT_RETENTION_SECONDS = 86400;
const MIN_AUDIT_RETENTION_SECONDS = 300;
const MAX_AUDIT_RETENTION_SECONDS = 2592000;

export type ToolInvocationAuditPolicy = {
  readonly maxEntries: number;
  readonly retentionSeconds: number;
};

export type ToolInvocationAuditStats = ToolInvocationAuditPolicy & {
  readonly recordCount: number;
  readonly oldestFinishedAt?: string;
  readonly newestFinishedAt?: string;
};

const parseAuditLimit = (): number => {
  const configured = process.env["SG_APIS_AUDIT_MAX_ENTRIES"];
  if (configured === undefined || configured.trim() === "") {
    return DEFAULT_MAX_AUDIT_ENTRIES;
  }

  const parsed = Number.parseInt(configured, 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_MAX_AUDIT_ENTRIES;
  }

  if (parsed < MIN_AUDIT_ENTRIES) {
    return MIN_AUDIT_ENTRIES;
  }
  if (parsed > MAX_AUDIT_ENTRIES_HARD_CAP) {
    return MAX_AUDIT_ENTRIES_HARD_CAP;
  }
  return parsed;
};

const parseAuditRetentionSeconds = (): number => {
  const configured = process.env["SG_APIS_AUDIT_RETENTION_SEC"];
  if (configured === undefined || configured.trim() === "") {
    return DEFAULT_AUDIT_RETENTION_SECONDS;
  }

  const parsed = Number.parseInt(configured, 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_AUDIT_RETENTION_SECONDS;
  }

  if (parsed < MIN_AUDIT_RETENTION_SECONDS) {
    return MIN_AUDIT_RETENTION_SECONDS;
  }
  if (parsed > MAX_AUDIT_RETENTION_SECONDS) {
    return MAX_AUDIT_RETENTION_SECONDS;
  }
  return parsed;
};

const auditRecords: ToolInvocationAuditRecord[] = [];
const byTraceId = new Map<string, ToolInvocationAuditRecord>();
const byRequestId = new Map<string, ToolInvocationAuditRecord>();

const removeRecordAt = (index: number): void => {
  const [removed] = auditRecords.splice(index, 1);
  if (removed === undefined) {
    return;
  }
  if (byTraceId.get(removed.traceId) === removed) {
    byTraceId.delete(removed.traceId);
  }
  if (byRequestId.get(removed.requestId) === removed) {
    byRequestId.delete(removed.requestId);
  }
};

const getAuditPolicy = (): ToolInvocationAuditPolicy => {
  return {
    maxEntries: parseAuditLimit(),
    retentionSeconds: parseAuditRetentionSeconds(),
  };
};

const purgeExpiredAuditRecords = (policy: ToolInvocationAuditPolicy): void => {
  const retentionMs = policy.retentionSeconds * 1000;
  const cutoffMs = Date.now() - retentionMs;
  for (let index = auditRecords.length - 1; index >= 0; index--) {
    const record = auditRecords[index];
    if (record === undefined) {
      continue;
    }
    const finishedAtMs = Date.parse(record.finishedAt);
    if (!Number.isFinite(finishedAtMs) || finishedAtMs < cutoffMs) {
      removeRecordAt(index);
    }
  }
};

const trimAuditStore = (policy: ToolInvocationAuditPolicy): void => {
  purgeExpiredAuditRecords(policy);
  const maxEntries = policy.maxEntries;
  while (auditRecords.length > maxEntries) {
    removeRecordAt(0);
  }
};

const toStoredError = (error: ToolErrorPayload): NonNullable<ToolInvocationAuditRecord["error"]> => {
  return {
    code: error.code,
    source: error.source,
    message: error.message,
    retryable: error.retryable,
    ...(error.statusCode === undefined ? {} : { statusCode: error.statusCode }),
    ...(error.category === undefined ? {} : { category: error.category }),
    ...(error.severity === undefined ? {} : { severity: error.severity }),
    ...(error.suggestedAction === undefined ? {} : { suggestedAction: error.suggestedAction }),
  };
};

export const recordToolInvocationAudit = (
  params: Readonly<{
    traceId: string;
    requestId: string;
    tool: string;
    status: ToolInvocationStatus;
    startedAt: string;
    finishedAt: string;
    durationMs: number;
    error?: ToolErrorPayload;
  }>,
): ToolInvocationAuditRecord => {
  const record: ToolInvocationAuditRecord = {
    traceId: params.traceId,
    requestId: params.requestId,
    tool: params.tool,
    status: params.status,
    startedAt: params.startedAt,
    finishedAt: params.finishedAt,
    durationMs: Math.max(0, Math.round(params.durationMs)),
    ...(params.error === undefined ? {} : { error: toStoredError(params.error) }),
  };

  auditRecords.push(record);
  byTraceId.set(record.traceId, record);
  byRequestId.set(record.requestId, record);
  trimAuditStore(getAuditPolicy());
  return record;
};

export const getToolInvocationAuditByTraceId = (traceId: string): ToolInvocationAuditRecord | null => {
  trimAuditStore(getAuditPolicy());
  return byTraceId.get(traceId) ?? null;
};

export const getToolInvocationAuditByRequestId = (requestId: string): ToolInvocationAuditRecord | null => {
  trimAuditStore(getAuditPolicy());
  return byRequestId.get(requestId) ?? null;
};

export const listRecentToolInvocationAudits = (limit = 20): readonly ToolInvocationAuditRecord[] => {
  trimAuditStore(getAuditPolicy());
  const safeLimit = Math.min(Math.max(1, Math.floor(limit)), 500);
  return [...auditRecords].slice(-safeLimit).reverse();
};

export const getToolInvocationAuditStats = (): ToolInvocationAuditStats => {
  const policy = getAuditPolicy();
  trimAuditStore(policy);
  const oldest = auditRecords[0];
  const newest = auditRecords[auditRecords.length - 1];
  return {
    ...policy,
    recordCount: auditRecords.length,
    ...(oldest === undefined ? {} : { oldestFinishedAt: oldest.finishedAt }),
    ...(newest === undefined ? {} : { newestFinishedAt: newest.finishedAt }),
  };
};

export const clearToolInvocationAuditStoreForTests = (): void => {
  auditRecords.length = 0;
  byTraceId.clear();
  byRequestId.clear();
};
