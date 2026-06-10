import { randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import Database from "better-sqlite3";
import { ApiError, resolveStatePath } from "@swee-sg/shared";
import { hashAuditValue, sanitizeAuditValue } from "./audit-store.js";
import type { SplunkPolicySimulation, SplunkSearchPolicyInput } from "./splunk-policy-simulator.js";
import { hashSplunkApprovalRequest, normalizeSplunkSearchRequest } from "./splunk-policy-simulator.js";

export type ShieldApprovalStatus = "pending" | "approved" | "rejected" | "expired";

export type ShieldApprovalRecord = {
  readonly approvalId: string;
  readonly toolName: string;
  readonly status: ShieldApprovalStatus;
  readonly createdAt: string;
  readonly expiresAt: string;
  readonly reviewedAt: string | null;
  readonly reviewer: string | null;
  readonly comment: string | null;
  readonly requestHash: string;
  readonly request: unknown;
  readonly risk: unknown;
  readonly decision: unknown;
};

type ApprovalRow = {
  readonly approval_id: string;
  readonly tool_name: string;
  readonly status: ShieldApprovalStatus;
  readonly created_at: string;
  readonly expires_at: string;
  readonly reviewed_at: string | null;
  readonly reviewer: string | null;
  readonly comment: string | null;
  readonly request_hash: string;
  readonly request_json: string;
  readonly risk_json: string;
  readonly decision_json: string | null;
};

type TableInfoRow = {
  readonly name: string;
};

export const resolveApprovalMode = (): "off" | "queue" =>
  process.env["SWEE_SHIELD_APPROVAL_MODE"]?.trim().toLowerCase() === "queue" ? "queue" : "off";

const resolveApprovalTtlMs = (): number => {
  const configured = Number(process.env["SWEE_SHIELD_APPROVAL_TTL_SEC"] ?? 900);
  return Number.isFinite(configured) && configured > 0 ? configured * 1000 : 900_000;
};

const effectiveStatus = (status: ShieldApprovalStatus, expiresAt: string): ShieldApprovalStatus => {
  if (status === "pending" && Date.parse(expiresAt) <= Date.now()) return "expired";
  return status;
};

const rowToRecord = (row: ApprovalRow): ShieldApprovalRecord => ({
  approvalId: row.approval_id,
  toolName: row.tool_name,
  status: effectiveStatus(row.status, row.expires_at),
  createdAt: row.created_at,
  expiresAt: row.expires_at,
  reviewedAt: row.reviewed_at,
  reviewer: row.reviewer,
  comment: row.comment,
  requestHash: row.request_hash,
  request: JSON.parse(row.request_json) as unknown,
  risk: JSON.parse(row.risk_json) as unknown,
  decision: row.decision_json === null ? null : JSON.parse(row.decision_json) as unknown,
});

export class ShieldApprovalStore {
  private readonly db: Database.Database;

  constructor(dbPath = resolveStatePath("shield-approvals.db")) {
    if (dbPath !== ":memory:") {
      mkdirSync(dirname(dbPath), { recursive: true });
    }
    this.db = new Database(dbPath);
    this.db.pragma("journal_mode = WAL");
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS shield_approval (
        approval_id TEXT PRIMARY KEY,
        tool_name TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        reviewed_at TEXT,
        reviewer TEXT,
        comment TEXT,
        request_hash TEXT NOT NULL,
        request_json TEXT NOT NULL,
        risk_json TEXT NOT NULL,
        decision_json TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_shield_approval_status ON shield_approval(status);
      CREATE INDEX IF NOT EXISTS idx_shield_approval_tool ON shield_approval(tool_name);
      CREATE INDEX IF NOT EXISTS idx_shield_approval_request ON shield_approval(request_hash);
    `);
    this.migrate();
  }

  private migrate(): void {
    const columns = new Set(
      (this.db.prepare("PRAGMA table_info(shield_approval)").all() as TableInfoRow[]).map((row) => row.name),
    );
    if (!columns.has("request_hash")) {
      this.db.exec("ALTER TABLE shield_approval ADD COLUMN request_hash TEXT NOT NULL DEFAULT ''");
    }
  }

  create(params: {
    readonly toolName: string;
    readonly request: SplunkSearchPolicyInput;
    readonly risk: SplunkPolicySimulation;
  }): ShieldApprovalRecord {
    const createdAt = new Date();
    const expiresAt = new Date(createdAt.getTime() + resolveApprovalTtlMs());
    const request = normalizeSplunkSearchRequest(params.request);
    const requestHash = hashSplunkApprovalRequest(request);
    const existing = this.findPendingByHash(params.toolName, requestHash);
    if (existing !== null) return existing;
    const approvalId = randomUUID();
    this.db.prepare(`
      INSERT INTO shield_approval (
        approval_id, tool_name, status, created_at, expires_at, reviewed_at,
        reviewer, comment, request_hash, request_json, risk_json, decision_json
      )
      VALUES (
        @approvalId, @toolName, 'pending', @createdAt, @expiresAt, NULL,
        NULL, NULL, @requestHash, @requestJson, @riskJson, NULL
      )
    `).run({
      approvalId,
      toolName: params.toolName,
      createdAt: createdAt.toISOString(),
      expiresAt: expiresAt.toISOString(),
      requestHash,
      requestJson: JSON.stringify(sanitizeAuditValue(request)),
      riskJson: JSON.stringify(params.risk),
    });
    return this.get(approvalId)!;
  }

  private findPendingByHash(toolName: string, requestHash: string): ShieldApprovalRecord | null {
    const row = this.db.prepare(`
      SELECT * FROM shield_approval
      WHERE tool_name = ? AND request_hash = ? AND status = 'pending'
      ORDER BY created_at DESC LIMIT 1
    `).get(toolName, requestHash) as ApprovalRow | undefined;
    const record = row === undefined ? null : rowToRecord(row);
    return record?.status === "pending" ? record : null;
  }

  get(approvalId: string): ShieldApprovalRecord | null {
    const row = this.db.prepare("SELECT * FROM shield_approval WHERE approval_id = ?").get(approvalId) as ApprovalRow | undefined;
    return row === undefined ? null : rowToRecord(row);
  }

  list(params: {
    readonly status?: ShieldApprovalStatus;
    readonly toolName?: string;
    readonly limit?: number;
  } = {}): readonly ShieldApprovalRecord[] {
    const clauses: string[] = [];
    const values: Record<string, unknown> = { limit: Math.min(Math.max(params.limit ?? 25, 1), 100) };
    if (params.toolName !== undefined) {
      clauses.push("tool_name = @toolName");
      values.toolName = params.toolName;
    }
    if (params.status !== undefined && params.status !== "expired") {
      clauses.push("status = @status");
      values.status = params.status;
    }
    const where = clauses.length === 0 ? "" : `WHERE ${clauses.join(" AND ")}`;
    const rows = this.db.prepare(`SELECT * FROM shield_approval ${where} ORDER BY created_at DESC LIMIT @limit`).all(values) as ApprovalRow[];
    const records = rows.map((row) => rowToRecord(row));
    return params.status === "expired" ? records.filter((record) => record.status === "expired") : records;
  }

  decide(params: {
    readonly approvalId: string;
    readonly decision: "approved" | "rejected";
    readonly reviewer?: string;
    readonly comment?: string;
  }): ShieldApprovalRecord {
    const existing = this.get(params.approvalId);
    if (existing === null) {
      throw new ApiError({
        apiName: "swee_shield_approval",
        source: "Swee Shield Approval",
        statusCode: 404,
        code: "SHIELD_APPROVAL_NOT_FOUND",
        message: "Approval request was not found.",
        retryable: false,
      });
    }
    if (existing.status !== "pending") {
      throw new ApiError({
        apiName: "swee_shield_approval",
        source: "Swee Shield Approval",
        statusCode: 409,
        code: "SHIELD_APPROVAL_NOT_PENDING",
        message: `Approval request is ${existing.status}.`,
        retryable: false,
        details: { approvalId: params.approvalId, status: existing.status },
      });
    }
    const reviewedAt = new Date().toISOString();
    const decisionPayload = {
      decision: params.decision,
      reviewedAt,
      reviewer: params.reviewer ?? null,
      comment: params.comment ?? null,
      decisionHash: hashAuditValue({ approvalId: params.approvalId, decision: params.decision, reviewedAt }),
    };
    this.db.prepare(`
      UPDATE shield_approval
      SET status = @status, reviewed_at = @reviewedAt, reviewer = @reviewer,
        comment = @comment, decision_json = @decisionJson
      WHERE approval_id = @approvalId
    `).run({
      approvalId: params.approvalId,
      status: params.decision,
      reviewedAt,
      reviewer: params.reviewer ?? null,
      comment: params.comment ?? null,
      decisionJson: JSON.stringify(decisionPayload),
    });
    return this.get(params.approvalId)!;
  }

  requireApproved(params: {
    readonly approvalId: string;
    readonly toolName: string;
    readonly request: SplunkSearchPolicyInput;
  }): ShieldApprovalRecord {
    const record = this.get(params.approvalId);
    const requestHash = hashSplunkApprovalRequest(params.request);
    if (record === null) {
      throw approvalError("SHIELD_APPROVAL_NOT_FOUND", "Approval request was not found.", params.approvalId);
    }
    if (record.status !== "approved") {
      throw approvalError("SHIELD_APPROVAL_NOT_APPROVED", `Approval request is ${record.status}.`, params.approvalId);
    }
    if (record.toolName !== params.toolName || record.requestHash !== requestHash) {
      throw approvalError("SHIELD_APPROVAL_MISMATCH", "Approval request does not match this Splunk search.", params.approvalId);
    }
    return record;
  }
}

const approvalError = (code: string, message: string, approvalId: string): ApiError =>
  new ApiError({
    apiName: "swee_shield_approval",
    source: "Swee Shield Approval",
    statusCode: code === "SHIELD_APPROVAL_NOT_FOUND" ? 404 : 409,
    code,
    message,
    retryable: false,
    details: { approvalId },
  });

let defaultStore: ShieldApprovalStore | null = null;

export const getShieldApprovalStore = (): ShieldApprovalStore => {
  defaultStore ??= new ShieldApprovalStore();
  return defaultStore;
};

export const setShieldApprovalStoreForTesting = (store: ShieldApprovalStore | null): void => {
  defaultStore = store;
};
