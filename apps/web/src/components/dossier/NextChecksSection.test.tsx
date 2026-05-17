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
      nextChecks: [
        {
          input: {
            entityName: "DBS PTE. LTD.",
            jurisdictionCode: "sg",
            uen: "197700546G",
          },
          reason: "Cross-link the entity to OpenCorporates identifiers without inferring ownership or control.",
          tool: "sg_opencorporates_links",
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
    expect(html).not.toContain("{&quot;");
  });
});
