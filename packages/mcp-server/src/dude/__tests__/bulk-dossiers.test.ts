import { describe, expect, it } from "vitest";

import { buildBulkDossierResponse, parseBulkDossierItems } from "../bulk-dossiers.js";
import type { AnalystMemoDossier } from "../analyst-memo.js";
import type { CddOrchestratorResponse } from "../cdd-orchestrator.js";

const dossier: AnalystMemoDossier = {
  evidence: [{ label: "Matched modules", source: "Resolver", value: 1 }],
  freshness: [{ observedAt: "2026-05-15T00:00:00.000Z", source: "ACRA" }],
  gaps: [{ code: "GEBIZ_NO_MATCH", message: "No GeBIZ match." }],
  limits: [{ code: "PUBLIC_DATA_ONLY", message: "Public data only." }],
  provenance: [{
    authRequired: false,
    coverage: "ACRA evidence.",
    recordCount: 1,
    source: "ACRA",
    tool: "sg_acra_entities",
  }],
  records: {
    quality: { dossierConfidence: { level: "high" } },
    resolution: { matchedModules: ["acra"] },
  },
  riskFlags: [{ code: "PARTIAL_MODULE_COVERAGE", message: "Partial coverage.", severity: "medium", source: "Resolver" }],
  summary: [
    { label: "Entity", source: "ACRA", value: "DBS BANK LTD" },
    { label: "UEN", source: "ACRA", value: "03591300B" },
    { label: "Entity status", source: "ACRA", value: "Live" },
  ],
  title: "Business Dossier",
};

const orchestratorResponse = (record: AnalystMemoDossier): CddOrchestratorResponse => ({
  dossier: record,
  generatedAt: "2026-05-15T00:00:00.000Z",
  memo: {
    configured: false,
    gaps: record.gaps,
    generatedAt: "2026-05-15T00:00:00.000Z",
    limits: record.limits,
    model: "gpt-4o",
    provider: "openai",
    reason: {
      code: "AI_PROVIDER_NOT_CONFIGURED",
      message: "AI provider is not configured.",
    },
    status: "unavailable",
  },
  orchestration: {
    acraSectorHints: [],
    effectiveSectorHints: [],
    officialModules: ["acra"],
    reranDossierForWebSectorHints: false,
    status: "ready",
    strategy: "acra_then_sector_then_supplemental_memo",
    supplementalTools: ["sg_relationship_graph"],
    stages: [{
      detail: "Canonical entity resolved through ACRA before downstream CDD enrichment.",
      id: "acra_identity",
      label: "ACRA identity lookup",
      status: "completed",
      tools: ["sg_acra_entities"],
    }],
    limits: ["Fixture orchestrator response."],
    webSectorHints: [],
  },
  peopleDiscovery: {
    configured: false,
    entityName: "DBS BANK LTD",
    limits: ["TinyFish Search is not configured on the server."],
    query: "\"DBS BANK\" Singapore employees leadership directors LinkedIn",
    results: [],
    suggestedActions: [],
    uen: "03591300B",
  },
  webPresence: {
    configured: false,
    limits: ["TinyFish Search is not configured on the server."],
    possibleOfficialWebsite: null,
    query: "DBS BANK LTD 03591300B",
    results: [],
  },
});

describe("bulk dossiers", () => {
  it("normalizes row-level parse errors before execution", () => {
    const parsed = parseBulkDossierItems({
      items: ["03591300B", "", { identifier: "x".repeat(129) }],
    });

    expect(parsed.items).toEqual([{ identifier: "03591300B", index: 0 }]);
    expect(parsed.errors).toMatchObject([
      { code: "EMPTY_IDENTIFIER", index: 1 },
      { code: "IDENTIFIER_TOO_LONG", index: 2 },
    ]);
  });

  it("returns partial-failure rows without aborting the batch", async () => {
    const response = await buildBulkDossierResponse(
      { items: ["03591300B", "FAIL"] },
      async (input) => {
        if ("entityName" in input) throw new Error("upstream failed");
        return orchestratorResponse(dossier);
      },
      "2026-05-15T00:00:00.000Z",
    );

    expect(response.executedCount).toBe(2);
    expect(response.rows[0]).toMatchObject({
      confidence: "high",
      entity: "DBS BANK LTD",
      risk: "medium",
      status: "success",
    });
    expect(response.rows[0]).toMatchObject({
      memo: { status: "unavailable" },
      orchestration: { strategy: "acra_then_sector_then_supplemental_memo" },
      webPresence: { configured: false },
    });
    expect(response.rows[1]).toMatchObject({
      gapCodes: ["DOSSIER_FAILED"],
      status: "error",
      upstreamFailure: true,
    });
  });

  it("accepts up to 200 rows for workspace-backed bulk runs", () => {
    const parsed = parseBulkDossierItems({
      items: Array.from({ length: 200 }, (_, index) => `COMPANY ${index}`),
    });
    expect(parsed.items).toHaveLength(200);
    expect(parsed.errors).toHaveLength(0);

    expect(parseBulkDossierItems({
      items: Array.from({ length: 201 }, (_, index) => `COMPANY ${index}`),
    }).errors).toEqual(expect.arrayContaining([
      expect.objectContaining({
        message: "Only the first 200 rows can be executed in one batch.",
      }),
    ]));
  });
});
