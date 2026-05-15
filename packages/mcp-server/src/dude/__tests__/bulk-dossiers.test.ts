import { describe, expect, it } from "vitest";

import { buildBulkDossierResponse, parseBulkDossierItems } from "../bulk-dossiers.js";
import type { AnalystMemoDossier } from "../analyst-memo.js";

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
        return { structuredContent: { record: dossier } };
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
    expect(response.rows[1]).toMatchObject({
      gapCodes: ["DOSSIER_FAILED"],
      status: "error",
      upstreamFailure: true,
    });
  });
});
