import { createHash, randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import Database from "better-sqlite3";
import { resolveStatePath } from "@swee-sg/shared";
import type { ShieldAuditRecord, ShieldAuditStatus, ShieldPolicyDecision, ToolErrorPayload } from "@swee-sg/shared";

type ShieldAuditRow = {
  readonly audit_id: string;
  readonly trace_id: string;
  readonly request_id: string;
  readonly tool_name: string;
  readonly decision_json: string;
  readonly status: ShieldAuditStatus;
  readonly started_at: string;
  readonly finished_at: string;
  readonly duration_ms: number;
  readonly input_hash: string;
  readonly output_hash: string | null;
  readonly error_json: string | null;
};

const SENSITIVE_KEY_PATTERN = /(password|secret|token|api[_-]?key|authorization|cookie|session|bearer)/i;

const stableStringify = (value: unknown): string => {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
};

export const redactForShieldAudit = (value: unknown): unknown => {
  if (Array.isArray(value)) {
    return value.map((item) => redactForShieldAudit(item));
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [
      key,
      SENSITIVE_KEY_PATTERN.test(key) ? "[redacted]" : redactForShieldAudit(item),
    ]));
  }
  return value;
};

export const hashForShieldAudit = (value: unknown): string =>
  createHash("sha256").update(stableStringify(redactForShieldAudit(value))).digest("hex");

const toRecord = (row: ShieldAuditRow): ShieldAuditRecord => ({
  auditId: row.audit_id,
  traceId: row.trace_id,
  requestId: row.request_id,
  toolName: row.tool_name,
  decision: JSON.parse(row.decision_json) as ShieldPolicyDecision,
  status: row.status,
  startedAt: row.started_at,
  finishedAt: row.finished_at,
  durationMs: row.duration_ms,
  inputHash: row.input_hash,
  outputHash: row.output_hash,
  ...(row.error_json === null ? {} : { error: JSON.parse(row.error_json) as ToolErrorPayload }),
});

export class ShieldAuditStore {
  readonly #db: Database.Database;

  constructor(dbPath = process.env["SWEE_SHIELD_AUDIT_DB_PATH"] ?? resolveStatePath("shield-audit.db")) {
    if (dbPath !== ":memory:") {
      mkdirSync(dirname(dbPath), { recursive: true });
    }
    this.#db = new Database(dbPath);
    this.#db.pragma("journal_mode = WAL");
    this.#db.exec(`
      CREATE TABLE IF NOT EXISTS shield_audit (
        audit_id TEXT PRIMARY KEY,
        trace_id TEXT NOT NULL,
        request_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        duration_ms INTEGER NOT NULL,
        input_hash TEXT NOT NULL,
        output_hash TEXT,
        error_json TEXT
      );
      CREATE INDEX IF NOT EXISTS shield_audit_trace_idx ON shield_audit(trace_id);
      CREATE INDEX IF NOT EXISTS shield_audit_request_idx ON shield_audit(request_id);
      CREATE INDEX IF NOT EXISTS shield_audit_tool_idx ON shield_audit(tool_name);
      CREATE INDEX IF NOT EXISTS shield_audit_finished_idx ON shield_audit(finished_at);
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
    const traceId = params.traceId ?? randomUUID();
    const requestId = params.requestId ?? randomUUID();
    const inputHash = hashForShieldAudit(params.input);
    const outputHash = params.output === undefined ? null : hashForShieldAudit(params.output);
    this.#db.prepare(`
      INSERT INTO shield_audit (
        audit_id,
        trace_id,
        request_id,
        tool_name,
        decision_json,
        status,
        started_at,
        finished_at,
        duration_ms,
        input_hash,
        output_hash,
        error_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      auditId,
      traceId,
      requestId,
      params.toolName,
      JSON.stringify(params.decision),
      params.status,
      params.startedAt,
      params.finishedAt,
      Math.max(0, Math.round(params.durationMs)),
      inputHash,
      outputHash,
      params.error === undefined ? null : JSON.stringify(redactForShieldAudit(params.error)),
    );
    const record = this.get(auditId);
    if (record === null) {
      throw new Error(`Failed to persist Shield audit ${auditId}.`);
    }
    return record;
  }

  get(id: string): ShieldAuditRecord | null {
    const row = this.#db.prepare("SELECT * FROM shield_audit WHERE audit_id = ? OR trace_id = ? OR request_id = ?")
      .get(id, id, id) as ShieldAuditRow | undefined;
    return row === undefined ? null : toRecord(row);
  }

  recent(limit = 50): readonly ShieldAuditRecord[] {
    const rows = this.#db.prepare("SELECT * FROM shield_audit ORDER BY finished_at DESC LIMIT ?")
      .all(Math.min(Math.max(1, Math.floor(limit)), 500)) as ShieldAuditRow[];
    return rows.map(toRecord);
  }

  clearForTests(): void {
    this.#db.exec("DELETE FROM shield_audit");
  }
}

export const shieldAuditStore = new ShieldAuditStore();
