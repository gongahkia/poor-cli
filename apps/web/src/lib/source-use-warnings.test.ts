import { describe, expect, it } from "vitest";

import {
  buildSourceUseWarnings,
  buildSourceUseWarningsFromSources,
  formatSourceUseWarnings,
} from "@/lib/source-use-warnings";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  evidence: [{ label: "ACRA matches", source: "ACRA", value: 1 }],
  freshness: [],
  gaps: [],
  limits: [],
  provenance: [{
    authRequired: false,
    coverage: "Entity identity",
    recordCount: 1,
    source: "ACRA",
    tool: "sg_acra_entities",
  }],
  records: { acra: [{ entityName: "DBS BANK LTD", uen: "03591300B" }] },
  summary: [{ label: "Entity", source: "ACRA", value: "DBS BANK LTD" }],
  title: "Business Dossier",
};

describe("source-use warnings", () => {
  it("adds paid hosted source-use language when ACRA evidence is present", () => {
    const warnings = buildSourceUseWarnings({ dossier });

    expect(warnings).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: "acra_source_use",
        message: expect.stringContaining("hosted paid redistribution"),
        triggeredBy: ["ACRA"],
      }),
    ]));
  });

  it("labels supplemental providers as analyst-review evidence", () => {
    const warnings = buildSourceUseWarnings({
      dossier: {
        ...dossier,
        provenance: [
          ...dossier.provenance,
          {
            authRequired: true,
            coverage: "Candidate screening",
            evidenceType: "web_discovery",
            recordCount: 1,
            source: "OpenSanctions",
            tool: "sg_sanctions_screen",
          },
        ],
      },
    });

    expect(formatSourceUseWarnings(warnings)).toContain("analyst-review signals");
    expect(formatSourceUseWarnings(warnings)).toContain("not official registry facts");
    expect(formatSourceUseWarnings(warnings)).toContain("sanctions clearance");
  });

  it("can derive warnings from compact export source lists", () => {
    const warnings = buildSourceUseWarningsFromSources(["ACRA", "OpenCorporates"]);

    expect(warnings.map((warning) => warning.id)).toEqual([
      "acra_source_use",
      "supplemental_analyst_review",
    ]);
  });
});
