import { describe, expect, it } from "vitest";

import {
  buildSingleDossierCsvRow,
  buildSingleDossierJsonPayload,
} from "@/lib/export/structured";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  evidence: [{ label: "ACRA matches", source: "ACRA", value: 1 }],
  freshness: [],
  gaps: [{ code: "NO_MATCH", message: "No exact match." }],
  limits: [{ code: "PUBLIC_DATA_ONLY", message: "Public data only." }],
  provenance: [{ authRequired: false, coverage: "Entity identity", recordCount: 1, source: "ACRA", tool: "sg_acra_entities" }],
  records: { acra: [{ entityName: "Example Pte Ltd" }] },
  summary: [{ label: "Entity", value: "Example Pte Ltd" }],
  title: "Business Dossier",
};

describe("structured dossier exports", () => {
  it("includes compliance-use limitations and a manifest in JSON exports", async () => {
    await expect(buildSingleDossierJsonPayload({
      dossier,
      generatedAt: "2026-05-16T00:00:00.000Z",
    })).resolves.toMatchObject({
      complianceUse: {
        complianceUseNotice: expect.stringContaining("not legal"),
        pdpaRuleMappingNotice: expect.stringContaining("not a legal opinion"),
        publicDataLimitsNotice: expect.stringContaining("Missing public-data evidence is a gap"),
      },
      generatedAt: "2026-05-16T00:00:00.000Z",
      limits: dossier.limits,
      manifest: {
        generatedAt: "2026-05-16T00:00:00.000Z",
        schemaVersion: "dude-export-manifest/v1",
        signature: {
          algorithm: "sha256",
          value: expect.any(String),
        },
      },
      sourceUseWarnings: [expect.objectContaining({
        id: "acra_source_use",
        message: expect.stringContaining("hosted paid redistribution"),
      })],
    });
  });

  it("includes compliance-use limitations in CSV rows", () => {
    const row = buildSingleDossierCsvRow(dossier, "2026-05-16T00:00:00.000Z");

    expect(row).toMatchObject({
      complianceUseNotice: expect.stringContaining("licensed compliance advice"),
      generatedAt: "2026-05-16T00:00:00.000Z",
      limits: "PUBLIC_DATA_ONLY: Public data only.",
      sourceUseWarnings: expect.stringContaining("ACRA source-use review required"),
    });
  });
});
