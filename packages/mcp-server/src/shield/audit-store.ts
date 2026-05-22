import { createHash, randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import Database from "better-sqlite3";
import type {
  ShieldAuditRecord,
  ShieldAuditStatus,
  ShieldPolicyDecision,
  ShieldReplayMetadata,
  ToolErrorPayload,
} from "@swee-sg/shared";
import { resolveStatePath } from "@swee-sg/shared";

const SECRET_KEY_PATTERN = /(authorization|accountkey|api[_-]?key|token|secret|password|credential)/i;

const stableStringify = (value: unknown): string => JSON.stringify(value, Object.keys(flattenKeys(value)).sort());

const flattenKeys = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object") return {};
  if (Array.isArray(value)) return Object.fromEntries(value.flatMap((item) => Object.entries(flattenKeys(item))));
  const entries: [string, unknown][] = [];
  for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
    entries.push([key, nested]);
    if (nested !== null && typeof nested === "object") {
      for (const [nestedKey, nestedValue] of Object.entries(flattenKeys(nested))) {
        entries.push([nestedKey, nestedValue]);
      }
    }
  }
  return Object.fromEntries(entries);
};

export const hashAuditValue = (value: unknown): string =>
  createHash("sha256").update(stableStringify(value)).digest("hex");

export const sanitizeAuditValue = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map((item) => sanitizeAuditValue(item));
  if (value === null || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, nested]) => [
      key,
      SECRET_KEY_PATTERN.test(key) ? "[redacted]" : sanitizeAuditValue(nested),
    ]),
  );
};

type AuditRow = {
  readonly audit_id: string;
  readonly trace_id: string | null;
  readonly request_id: string | null;
  readonly tool_name: string;
  readonly decision_json: string;
  readonly status: ShieldAuditStatus;
  readonly started_at: string;
  readonly finished_at: string;
  readonly duration_ms: number;
  readonly input_hash: string;
  readonly output_hash: string | null;
  readonly sanitized_input_json: string;
  readonly error_json: string | null;
};

const rowToRecord = (row: AuditRow): ShieldAuditRecord => ({
  auditId: row.audit_id,
  ...(row.trace_id === null ? {} : { traceId: row.trace_id }),
  ...(row.request_id === null ? {} : { requestId: row.request_id }),
  toolName: row.tool_name,
  decision: JSON.parse(row.decision_json) as ShieldPolicyDecision,
  status: row.status,
  startedAt: row.started_at,
  finishedAt: row.finished_at,
  durationMs: row.duration_ms,
  inputHash: row.input_hash,
  outputHash: row.output_hash,
  sanitizedInput: JSON.parse(row.sanitized_input_json) as unknown,
  ...(row.error_json === null ? {} : { error: JSON.parse(row.error_json) as ToolErrorPayload }),
});

export class ShieldAuditStore {
  private readonly db: Database.Database;

  constructor(dbPath = resolveStatePath("shield-audit.db")) {
    if (dbPath !== ":memory:") {
      mkdirSync(dirname(dbPath), { recursive: true });
    }
    this.db = new Database(dbPath);
    this.db.pragma("journal_mode = WAL");
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS shield_audit (
        audit_id TEXT PRIMARY KEY,
        trace_id TEXT,
        request_id TEXT,
        tool_name TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        duration_ms INTEGER NOT NULL,
        input_hash TEXT NOT NULL,
        output_hash TEXT,
        sanitized_input_json TEXT NOT NULL,
        error_json TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_shield_audit_trace ON shield_audit(trace_id);
      CREATE INDEX IF NOT EXISTS idx_shield_audit_request ON shield_audit(request_id);
      CREATE INDEX IF NOT EXISTS idx_shield_audit_tool ON shield_audit(tool_name);
      CREATE INDEX IF NOT EXISTS idx_shield_audit_started ON shield_audit(started_at);
    `);
  }

  record(params: {
    readonly traceId?: string;
    readonly requestId?: string;
    readonly toolName: string;
    readonly decision: ShieldPolicyDecision;
    readonly status: ShieldAuditStatus;
    readonly startedAt: string;
    readonly finishedAt: string;
    readonly durationMs: number;
    readonly input: unknown;
    readonly output?: unknown;
    readonly error?: ToolErrorPayload;
  }): ShieldAuditRecord {
    const auditId = randomUUID();
    const sanitizedInput = sanitizeAuditValue(params.input);
    const inputHash = hashAuditValue(sanitizedInput);
    const outputHash = params.output === undefined ? null : hashAuditValue(sanitizeAuditValue(params.output));
    this.db.prepare(`
      INSERT INTO shield_audit (
        audit_id, trace_id, request_id, tool_name, decision_json, status,
        started_at, finished_at, duration_ms, input_hash, output_hash,
        sanitized_input_json, error_json
      )
      VALUES (@auditId, @traceId, @requestId, @toolName, @decisionJson, @status,
        @startedAt, @finishedAt, @durationMs, @inputHash, @outputHash,
        @sanitizedInputJson, @errorJson)
    `).run({
      auditId,
      traceId: params.traceId ?? null,
      requestId: params.requestId ?? null,
      toolName: params.toolName,
      decisionJson: JSON.stringify(params.decision),
      status: params.status,
      startedAt: params.startedAt,
      finishedAt: params.finishedAt,
      durationMs: params.durationMs,
      inputHash,
      outputHash,
      sanitizedInputJson: JSON.stringify(sanitizedInput),
      errorJson: params.error === undefined ? null : JSON.stringify(sanitizeAuditValue(params.error)),
    });
    return this.get(auditId)!;
  }

  get(auditId: string): ShieldAuditRecord | null {
    const row = this.db.prepare("SELECT * FROM shield_audit WHERE audit_id = ?").get(auditId) as AuditRow | undefined;
    return row === undefined ? null : rowToRecord(row);
  }

  query(params: {
    readonly traceId?: string;
    readonly requestId?: string;
    readonly toolName?: string;
    readonly limit?: number;
  } = {}): readonly ShieldAuditRecord[] {
    const clauses: string[] = [];
    const values: Record<string, unknown> = { limit: Math.min(Math.max(params.limit ?? 25, 1), 100) };
    if (params.traceId !== undefined) {
      clauses.push("trace_id = @traceId");
      values.traceId = params.traceId;
    }
    if (params.requestId !== undefined) {
      clauses.push("request_id = @requestId");
      values.requestId = params.requestId;
    }
    if (params.toolName !== undefined) {
      clauses.push("tool_name = @toolName");
      values.toolName = params.toolName;
    }
    const where = clauses.length === 0 ? "" : `WHERE ${clauses.join(" AND ")}`;
    const rows = this.db.prepare(`SELECT * FROM shield_audit ${where} ORDER BY started_at DESC LIMIT @limit`).all(values) as AuditRow[];
    return rows.map((row) => rowToRecord(row));
  }

  getReplay(auditId: string): ShieldReplayMetadata | null {
    const record = this.get(auditId);
    if (record === null) return null;
    return {
      auditId: record.auditId,
      toolName: record.toolName,
      sanitizedInput: record.sanitizedInput,
      decision: record.decision,
      status: record.status,
      outputHash: record.outputHash,
      durationMs: record.durationMs,
    };
  }
}

let defaultStore: ShieldAuditStore | null = null;

export const getShieldAuditStore = (): ShieldAuditStore => {
  defaultStore ??= new ShieldAuditStore();
  return defaultStore;
};

export const setShieldAuditStoreForTesting = (store: ShieldAuditStore | null): void => {
  defaultStore = store;
};
