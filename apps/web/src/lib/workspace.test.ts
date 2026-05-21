import { describe, expect, it } from "vitest";

import { DEFAULT_AUTH_POLICY, evaluateLoginAttempt } from "@/lib/auth-policy";
import { createDefaultWorkspaceState, WorkspaceAccessError, assertWorkspaceAccess } from "@/lib/workspace";
import {
  addCddCaseNote,
  addCddCaseTask,
  addWatchlistItem,
  appendAuditEvent,
  appendBulkJob,
  attachDossierToCddCase,
  buildCddCaseId,
  buildCddCaseJsonPackage,
  createWorkspaceStore,
  getCddCase,
  importCddCaseJsonPackage,
  listAuditEvents,
  listCddCases,
  listDossierRecords,
  loadWorkspaceStore,
  recordWatchlistCheck,
  recordCddCaseExport,
  saveWorkspaceStore,
  setCddCaseTaskCompleted,
  summarizeBulkRisk,
  updateCddCaseStatus,
  upsertCddCase,
  upsertDossierRecord,
} from "@/lib/workspace-store";
import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BusinessDossier } from "@/types/dossier";

const fixtureDossier: BusinessDossier = {
  title: "Business Dossier",
  summary: [
    { label: "Entity", value: "DBS BANK LTD", source: "ACRA" },
    { label: "UEN", value: "03591300B", source: "ACRA" },
  ],
  evidence: [{ label: "Matched modules", value: 1, source: "Resolver" }],
  records: { resolution: { matchedModules: ["acra"] } },
  gaps: [],
  provenance: [{
    source: "ACRA",
    tool: "sg_acra_entities",
    coverage: "Company identity",
    authRequired: false,
    recordCount: 1,
  }],
  freshness: [{ source: "ACRA", observedAt: "2026-05-17T00:00:00.000Z" }],
  limits: [{ code: "PUBLIC_DATA_ONLY", message: "Public data only." }],
};

const fixtureMemo: AnalystMemoReady = {
  status: "ready",
  configured: true,
  provider: "openai",
  model: "gpt-test",
  generatedAt: "2026-05-17T00:05:00.000Z",
  evidenceMemo: [{ text: "ACRA identity was returned.", citationIds: ["C1"] }],
  riskRating: {
    level: "unknown",
    rationale: "Insufficient workflow review.",
    citationIds: ["C1"],
    confidenceBlockers: ["Analyst follow-up remains required."],
  },
  decisionAid: {
    nextSteps: ["Verify ownership and control documents."],
    confidenceBlockers: ["Beneficial ownership is not established from public data."],
    nonAdvisoryReminder: "No clearance is implied.",
  },
  citations: [{ id: "C1", label: "ACRA row", source: "ACRA", text: "DBS BANK LTD" }],
  gaps: [],
  limits: fixtureDossier.limits,
  rejectedClaims: [],
};

const createMemoryStorage = (): Storage => {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key: string) => data.get(key) ?? null,
    key: (index: number) => Array.from(data.keys())[index] ?? null,
    removeItem: (key: string) => {
      data.delete(key);
    },
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
  };
};

describe("workspace access control", () => {
  it("blocks role and cross-workspace access", () => {
    const state = createDefaultWorkspaceState("2026-05-17T00:00:00.000Z");
    const viewer = { ...state.activeSession, role: "viewer" as const };

    expect(() => assertWorkspaceAccess(viewer, "bulk:run")).toThrow(WorkspaceAccessError);
    expect(() => assertWorkspaceAccess(state.activeSession, "dossier:read", "other-workspace"))
      .toThrow("cannot access workspace");
  });

  it("keeps stored dossiers and audit events isolated by workspace", () => {
    const state = createDefaultWorkspaceState("2026-05-17T00:00:00.000Z");
    const otherSession = { ...state.activeSession, workspaceId: "other-workspace" };
    const store = upsertDossierRecord(createWorkspaceStore(state.activeSession.workspaceId), state.activeSession, {
      identifier: "03591300B",
      dossier: fixtureDossier,
      now: "2026-05-17T00:00:00.000Z",
    });
    const audited = appendAuditEvent(store, state.activeSession, {
      eventType: "dossier_generation",
      input: { identifier: "03591300B" },
      output: fixtureDossier,
      provenance: fixtureDossier.provenance,
      freshness: fixtureDossier.freshness,
      now: "2026-05-17T00:00:00.000Z",
    });

    expect(listDossierRecords(audited, state.activeSession)).toHaveLength(1);
    expect(listAuditEvents(audited, state.activeSession)).toHaveLength(1);
    expect(listAuditEvents(audited, state.activeSession)[0]).toMatchObject({
      inputSnapshot: { identifier: "03591300B" },
      outputSnapshot: { title: "Business Dossier" },
    });
    expect(listDossierRecords(audited, otherSession)).toHaveLength(0);
    expect(listAuditEvents(audited, otherSession)).toHaveLength(0);
  });
});

describe("CDD case workflow store", () => {
  it("creates cases, attaches dossier evidence, and keeps analyst work separate from source facts", () => {
    const state = createDefaultWorkspaceState("2026-05-17T00:00:00.000Z");
    const session = state.activeSession;
    const caseId = buildCddCaseId(session, { counterpartyIdentifier: "03591300B" });
    const dossierWithNextCheck: BusinessDossier = {
      ...fixtureDossier,
      analystFollowUps: [{
        action: "Screen aliases before handoff.",
        category: "supplemental_review",
        evidenceBasis: [{ detail: "Supplemental source was not reviewed.", kind: "source_gap", ref: "sourceCoverage.opensanctions", source: "OpenSanctions" }],
        id: "follow-up-01-recommended-supplemental-review-sourcecoverage-opensanctions",
        input: { name: "DBS BANK LTD" },
        priority: "recommended",
        reason: "OpenSanctions source coverage was skipped.",
        tool: "sg_sanctions_screen",
        whyThisMatters: "Supplemental sources are analyst-review evidence.",
      }],
      nextChecks: [{ tool: "sg_sanctions_screen", reason: "Screen aliases before handoff.", input: { name: "DBS BANK LTD" } }],
    };

    const created = upsertCddCase(createWorkspaceStore(session.workspaceId), session, {
      counterpartyIdentifier: "03591300B",
      now: "2026-05-17T00:00:00.000Z",
    });
    expect(getCddCase(created, session, caseId)).toMatchObject({
      status: "draft",
      storageScope: "browser_local",
      counterpartyIdentifier: "03591300B",
    });

    const withDossier = attachDossierToCddCase(created, session, caseId, {
      dossier: dossierWithNextCheck,
      memoState: fixtureMemo,
      generatedAt: "2026-05-17T00:05:00.000Z",
      now: "2026-05-17T00:06:00.000Z",
    });
    const withNote = addCddCaseNote(
      withDossier,
      session,
      caseId,
      "Analyst requested private ownership documents.",
      "2026-05-17T00:07:00.000Z",
    );
    const record = getCddCase(withNote, session, caseId);

    expect(record).toMatchObject({
      status: "in_review",
      dossier: { title: "Business Dossier" },
      memoState: { status: "ready" },
      evidencePack: {
        dossierTitle: "Business Dossier",
        analystFollowUps: [expect.objectContaining({ priority: "recommended" })],
      },
    });
    expect(record?.followUpTasks).toHaveLength(2);
    expect(record?.followUpTasks[0]).toMatchObject({
      source: "dossier_analyst_follow_up",
      title: "Recommended: Screen aliases before handoff.",
    });
    expect(record?.analystNotes[0]?.body).toContain("private ownership");
    expect(JSON.stringify(record?.evidencePack)).not.toContain("private ownership");
  });

  it("supports status transitions, task completion, persistence, and export records", () => {
    const state = createDefaultWorkspaceState("2026-05-17T00:00:00.000Z");
    const session = state.activeSession;
    const storage = createMemoryStorage();
    const caseId = buildCddCaseId(session, { counterpartyIdentifier: "03591300B" });
    const created = upsertCddCase(createWorkspaceStore(session.workspaceId), session, {
      counterpartyIdentifier: "03591300B",
      now: "2026-05-17T00:00:00.000Z",
    });
    const withTask = addCddCaseTask(created, session, caseId, {
      title: "Confirm signatory authority.",
      now: "2026-05-17T00:01:00.000Z",
    });
    const taskId = getCddCase(withTask, session, caseId)?.followUpTasks[0]?.id;
    expect(taskId).toBeDefined();

    const completed = setCddCaseTaskCompleted(
      withTask,
      session,
      caseId,
      taskId!,
      true,
      "2026-05-17T00:02:00.000Z",
    );
    const ready = updateCddCaseStatus(
      completed,
      session,
      caseId,
      "ready_for_export",
      "2026-05-17T00:03:00.000Z",
    );
    const exported = recordCddCaseExport(ready, session, caseId, {
      filename: "dude-cdd-report-03591300B.pdf",
      format: "pdf",
      packageType: "report_package",
      writingStyle: "audit_ready_formal",
      now: "2026-05-17T00:04:00.000Z",
    });

    saveWorkspaceStore(exported, storage);
    const restored = loadWorkspaceStore(storage);
    const record = getCddCase(restored, session, caseId);
    expect(record?.status).toBe("ready_for_export");
    expect(record?.followUpTasks[0]).toMatchObject({ status: "completed" });
    expect(record?.exports[0]).toMatchObject({
      filename: "dude-cdd-report-03591300B.pdf",
      statusAtExport: "ready_for_export",
    });
  });

  it("exports and imports case JSON as browser-local workflow state", () => {
    const state = createDefaultWorkspaceState("2026-05-17T00:00:00.000Z");
    const sourceSession = state.activeSession;
    const targetSession = { ...sourceSession, workspaceId: "target-workspace" };
    const caseId = buildCddCaseId(sourceSession, { counterpartyIdentifier: "03591300B" });
    const sourceStore = upsertCddCase(createWorkspaceStore(sourceSession.workspaceId), sourceSession, {
      counterpartyIdentifier: "03591300B",
      now: "2026-05-17T00:00:00.000Z",
    });
    const sourceCase = getCddCase(sourceStore, sourceSession, caseId);
    expect(sourceCase).not.toBeNull();

    const cddCasePackage = buildCddCaseJsonPackage(sourceCase!, "2026-05-17T00:01:00.000Z");
    expect(cddCasePackage).toMatchObject({
      schemaVersion: "dude-cdd-case/v1",
      storageScope: "browser_local",
    });
    expect(cddCasePackage.limits.join(" ")).toContain("does not imply approval");

    const imported = importCddCaseJsonPackage(createWorkspaceStore(targetSession.workspaceId), targetSession, {
      package: cddCasePackage,
      now: "2026-05-17T00:02:00.000Z",
    });
    expect(listCddCases(imported, targetSession)).toHaveLength(1);
    expect(listCddCases(imported, targetSession)[0]).toMatchObject({
      workspaceId: "target-workspace",
      counterpartyIdentifier: "03591300B",
    });
    expect(listCddCases(imported, targetSession)[0]?.auditEvents[0]).toMatchObject({
      eventType: "case_imported",
    });
  });

  it("applies case access checks", () => {
    const state = createDefaultWorkspaceState("2026-05-17T00:00:00.000Z");
    const viewer = { ...state.activeSession, role: "viewer" as const };
    const created = upsertCddCase(createWorkspaceStore(state.activeSession.workspaceId), state.activeSession, {
      counterpartyIdentifier: "03591300B",
      now: "2026-05-17T00:00:00.000Z",
    });
    const caseId = buildCddCaseId(state.activeSession, { counterpartyIdentifier: "03591300B" });

    expect(listCddCases(created, viewer)).toHaveLength(1);
    expect(() => upsertCddCase(created, viewer, { counterpartyIdentifier: "NEWCO" }))
      .toThrow(WorkspaceAccessError);
    expect(() => updateCddCaseStatus(created, viewer, caseId, "archived"))
      .toThrow(WorkspaceAccessError);
  });
});

describe("workspace jobs and watchlists", () => {
  it("persists 200-row bulk summaries and partial failure state", () => {
    const state = createDefaultWorkspaceState("2026-05-17T00:00:00.000Z");
    const rows = Array.from({ length: 200 }, (_, index) => ({
      index,
      input: `COMPANY ${index}`,
      status: index === 0 ? "error" as const : "success" as const,
      canonicalIdentifier: index === 0 ? null : `COMPANY ${index}`,
      entity: index === 0 ? null : `COMPANY ${index}`,
      uen: null,
      entityStatus: null,
      confidence: index === 0 ? null : "high",
      risk: index === 1 ? "high" as const : "none" as const,
      riskFlags: index === 1 ? ["ENTITY_NOT_ACTIVE"] : [],
      matchedModules: index === 0 ? [] : ["acra"],
      gapCodes: index === 0 ? ["DOSSIER_FAILED"] : [],
      upstreamFailure: index === 0,
      provenanceSources: index === 0 ? [] : ["ACRA"],
      generatedAt: "2026-05-17T00:00:00.000Z",
      ...(index === 0 ? { error: { code: "DOSSIER_FAILED", message: "failed" } } : { dossier: fixtureDossier }),
    }));

    const result = {
      generatedAt: "2026-05-17T00:00:00.000Z",
      maxItems: 200,
      requestedCount: 200,
      executedCount: 200,
      parseErrors: [],
      rows,
      limits: [],
    };
    expect(summarizeBulkRisk(result)).toMatchObject({ high: 1, upstreamFailures: 1 });
    expect(appendBulkJob(createWorkspaceStore(state.activeSession.workspaceId), state.activeSession, result).bulkJobs[0])
      .toMatchObject({ status: "partial_failure", requestedCount: 200 });
  });

  it("stores watchlist schedules and alert history", () => {
    const state = createDefaultWorkspaceState("2026-05-17T00:00:00.000Z");
    const store = addWatchlistItem(createWorkspaceStore(state.activeSession.workspaceId), state.activeSession, {
      identifier: "03591300B",
      modules: ["acra", "gebiz"],
      notificationChannel: "in_app",
      now: "2026-05-17T00:00:00.000Z",
    });
    const checked = recordWatchlistCheck(store, state.activeSession, store.watchlistItems[0]!.id, "2026-05-17T01:00:00.000Z");
    expect(checked.watchlistItems[0]!.nextRunAt).toBe("2026-05-18T01:00:00.000Z");
    expect(checked.alerts[0]).toMatchObject({ title: "Watchlist check queued" });
  });
});

describe("SSO and 2FA policy", () => {
  it("requires configured provider and second factor when policy demands it", () => {
    const state = createDefaultWorkspaceState("2026-05-17T00:00:00.000Z");

    expect(evaluateLoginAttempt(state, {
      ...DEFAULT_AUTH_POLICY,
      twoFactorPolicy: "required",
    }, {
      provider: "google",
      workspaceId: state.activeSession.workspaceId,
      email: "local-admin@dude.local",
      providerConfigured: true,
      secondFactorVerified: false,
    })).toMatchObject({
      allowed: false,
      blockers: ["SECOND_FACTOR_REQUIRED"],
    });

    expect(evaluateLoginAttempt(state, DEFAULT_AUTH_POLICY, {
      provider: "microsoft",
      workspaceId: state.activeSession.workspaceId,
      email: "local-admin@dude.local",
      providerConfigured: false,
      secondFactorVerified: true,
    })).toMatchObject({
      allowed: false,
      blockers: ["PROVIDER_NOT_CONFIGURED"],
    });
  });
});
