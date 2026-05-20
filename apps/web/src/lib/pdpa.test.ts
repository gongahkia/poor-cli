import { describe, expect, it } from "vitest";

import {
  buildPdpaChecklist,
  buildPdpaChecklistReport,
  pdpaCitations,
} from "@/lib/pdpa";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  evidence: [{ label: "ACRA matches", source: "ACRA", value: 1 }],
  freshness: [{
    observedAt: "2026-05-17T00:00:00.000Z",
    source: "ACRA",
    upstreamTimestamp: "2026-05-16",
  }],
  gaps: [],
  limits: [],
  matchConfidence: [{
    confidence: "exact",
    matchedOn: "uen",
    source: "ACRA",
  }],
  provenance: [{
    authRequired: false,
    coverage: "Entity identity",
    recordCount: 1,
    source: "ACRA",
    sourceUrl: "https://data.gov.sg/",
    tool: "sg_acra_entities",
  }],
  records: {
    acra: [{ entityName: "DBS BANK LTD", uen: "03591300B" }],
    resolution: {
      matchedModules: ["acra"],
      searchedModules: ["acra"],
    },
  },
  riskFlags: [],
  summary: [
    { label: "Entity", source: "ACRA", value: "DBS BANK LTD" },
    { label: "UEN", source: "ACRA", value: "03591300B" },
  ],
  title: "Business Dossier",
};

describe("PDPA checklist", () => {
  it("ties accuracy evidence to dossier identity, provenance, and confidence", () => {
    const items = buildPdpaChecklist(dossier);
    const accuracy = items.find((item) => item.id === "identity-accuracy");

    expect(accuracy?.status).toBe("evidence_available");
    expect(accuracy?.evidence.join("\n")).toContain("DBS BANK LTD");
    expect(accuracy?.evidence.join("\n")).toContain("ACRA");
    expect(accuracy?.citations).toContain(pdpaCitations.obligations);
  });

  it("flags upstream failures as blocked evidence", () => {
    const items = buildPdpaChecklist({
      ...dossier,
      gaps: [{ code: "ACRA_TIMEOUT", message: "ACRA timed out." }],
    });

    expect(items.find((item) => item.id === "identity-accuracy")?.status).toBe("blocked_by_gap");
    expect(items.find((item) => item.id === "protection-controls")?.gaps.join("\n")).toContain("ACRA_TIMEOUT");
  });

  it("builds a report with PDPC source citations and non-advice notice", () => {
    const report = buildPdpaChecklistReport(dossier, new Date("2026-05-17T00:00:00.000Z"));

    expect(report.citations.map((citation) => citation.url)).toContain(pdpaCitations.commonLapses.url);
    expect(report.nonAdviceNotice).toContain("not legal advice");
    expect(report.generatedAt).toBe("2026-05-17T00:00:00.000Z");
    expect(report.sourceUseWarnings).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "acra_source_use" }),
    ]));
  });
});
