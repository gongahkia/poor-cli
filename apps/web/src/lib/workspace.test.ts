import { describe, expect, it } from "vitest";

import { DEFAULT_AUTH_POLICY, evaluateLoginAttempt } from "@/lib/auth-policy";
import { createDefaultWorkspaceState, WorkspaceAccessError, assertWorkspaceAccess } from "@/lib/workspace";
import {
  addWatchlistItem,
  appendAuditEvent,
  appendBulkJob,
  createWorkspaceStore,
  listAuditEvents,
  listDossierRecords,
  recordWatchlistCheck,
  summarizeBulkRisk,
  upsertDossierRecord,
} from "@/lib/workspace-store";
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
    expect(listDossierRecords(audited, otherSession)).toHaveLength(0);
    expect(listAuditEvents(audited, otherSession)).toHaveLength(0);
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
