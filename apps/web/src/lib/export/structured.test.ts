import { describe, expect, it } from "vitest";

import {
  buildSingleDossierCsvRow,
  buildSingleDossierJsonPayload,
} from "@/lib/export/structured";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  evidence: [],
  freshness: [],
  gaps: [{ code: "NO_MATCH", message: "No exact match." }],
  limits: [{ code: "PUBLIC_DATA_ONLY", message: "Public data only." }],
  provenance: [],
  records: {},
  summary: [{ label: "Entity", value: "Example Pte Ltd" }],
  title: "Business Dossier",
};

describe("structured dossier exports", () => {
  it("includes compliance-use limitations in JSON exports", () => {
    expect(buildSingleDossierJsonPayload({
      dossier,
      generatedAt: "2026-05-16T00:00:00.000Z",
    })).toMatchObject({
      complianceUse: {
        complianceUseNotice: expect.stringContaining("not legal"),
        pdpaRuleMappingNotice: expect.stringContaining("not a legal opinion"),
        publicDataLimitsNotice: expect.stringContaining("Missing public-data evidence is a gap"),
      },
      generatedAt: "2026-05-16T00:00:00.000Z",
      limits: dossier.limits,
    });
  });

  it("includes compliance-use limitations in CSV rows", () => {
    const row = buildSingleDossierCsvRow(dossier, "2026-05-16T00:00:00.000Z");

    expect(row).toMatchObject({
      complianceUseNotice: expect.stringContaining("licensed compliance advice"),
      generatedAt: "2026-05-16T00:00:00.000Z",
      limits: "PUBLIC_DATA_ONLY: Public data only.",
    });
  });
});
