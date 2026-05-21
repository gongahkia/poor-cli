import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { NextChecksSection } from "@/components/dossier/NextChecksSection";
import type { BusinessDossier } from "@/types/dossier";

describe("NextChecksSection", () => {
  it("renders follow-up inputs as readable fields instead of raw JSON", () => {
    const dossier = {
      evidence: [],
      freshness: [],
      gaps: [],
      limits: [],
      analystFollowUps: [
        {
          action: "Cross-link the entity to OpenCorporates identifiers for analyst review.",
          category: "credential_required",
          evidenceBasis: [{
            detail: "OpenCorporates token is not configured.",
            kind: "source_gap",
            ref: "sourceCoverage.opencorporates",
            source: "OpenCorporates cross-links",
          }],
          id: "follow-up-01-recommended-credential-required-sourcecoverage-opencorporates",
          input: {
            entityName: "DBS PTE. LTD.",
            jurisdictionCode: "sg",
            uen: "197700546G",
          },
          priority: "recommended",
          reason: "OpenCorporates cross-links were blocked by missing credential(s): OPENCORPORATES_API_TOKEN.",
          tool: "sg_opencorporates_links",
          whyThisMatters: "The dossier is missing a configured source family.",
        },
      ],
      provenance: [],
      records: {},
      summary: [],
      title: "Business dossier",
    } satisfies BusinessDossier;

    const html = renderToStaticMarkup(<NextChecksSection dossier={dossier} />);

    expect(html).toContain("Entity Name");
    expect(html).toContain("Jurisdiction Code");
    expect(html).toContain("UEN");
    expect(html).toContain("197700546G");
    expect(html).toContain("Dossier follow-up");
    expect(html).toContain("To-do 01");
    expect(html).toContain("Recommended");
    expect(html).toContain("Credential Required");
    expect(html).toContain("Reviewed by analyst");
    expect(html).toContain("Inputs");
    expect(html).toContain("Why this matters");
    expect(html).toContain("Evidence basis");
    expect(html).toContain("1 open todo");
    expect(html).not.toContain("{&quot;");
  });
});
