import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FollowUpInputView, FollowUpResultView } from "@/components/dossier/FollowUpResultView";

describe("FollowUpResultView", () => {
  it("renders follow-up input as readable fields with a JSON copy affordance", () => {
    const html = renderToStaticMarkup(
      <FollowUpInputView
        input={{
          entityName: "DBS PTE. LTD.",
          jurisdictionCode: "sg",
          records: { acra: [{ entityName: "DBS PTE. LTD." }] },
          uen: "197700546G",
        }}
      />,
    );

    expect(html).toContain("Copy input JSON");
    expect(html).toContain("Entity Name");
    expect(html).toContain("Jurisdiction Code");
    expect(html).toContain("Dossier records (1 group)");
    expect(html).toContain("197700546G");
  });

  it("renders OpenCorporates results as summary sections instead of only raw JSON", () => {
    const html = renderToStaticMarkup(
      <FollowUpResultView
        result={{
          title: "OpenCorporates Cross-Links",
          summary: [
            { label: "Query", value: "197700546G", source: "Input" },
            { label: "Candidate links", value: 0, source: "OpenCorporates" },
          ],
          evidence: [{ label: "Ambiguous candidates", value: 0, source: "OpenCorporates" }],
          records: {
            companies: [],
            query: { entityName: "DBS PTE. LTD.", jurisdictionCode: "sg", uen: "197700546G" },
          },
          gaps: [{ code: "OPENCORPORATES_API_TOKEN_REQUIRED", message: "OpenCorporates cross-links require a token." }],
          provenance: [],
          freshness: [{ observedAt: "2026-05-20T00:00:00.000Z", source: "OpenCorporates" }],
          limits: [{ code: "NO_OWNERSHIP_CLAIMS", message: "Identifier cross-references only." }],
        }}
      />,
    );

    expect(html).toContain("Copy result JSON");
    expect(html).toContain("OpenCorporates Cross-Links");
    expect(html).toContain("Candidate links");
    expect(html).toContain("No companies returned");
    expect(html).toContain("OPENCORPORATES_API_TOKEN_REQUIRED");
    expect(html).toContain("Raw JSON");
  });

  it("renders relationship graph output as an SVG diagram with graph JSON copy", () => {
    const html = renderToStaticMarkup(
      <FollowUpResultView
        result={{
          title: "Relationship Graph",
          summary: [{ label: "Nodes", value: 2, source: "Graph builder" }],
          evidence: [{ label: "ACRA records inspected", value: 1, source: "ACRA" }],
          records: {
            graph: {
              nodes: [
                { id: "company:197700546G", kind: "company", label: "DBS PTE. LTD.", source: "ACRA" },
                { id: "address:anson-road", kind: "address", label: "anson road 079903", source: "ACRA" },
              ],
              edges: [
                {
                  confidence: "evidence",
                  evidence: "ACRA registered address fields.",
                  from: "company:197700546G",
                  kind: "registered_address",
                  to: "address:anson-road",
                },
              ],
            },
          },
          gaps: [],
          provenance: [],
          freshness: [],
          limits: [{ code: "NO_INFERRED_OWNERSHIP_OR_CONTROL", message: "No ownership or control inference." }],
        }}
      />,
    );

    expect(html).toContain("Relationship diagram");
    expect(html).toContain("Copy graph JSON");
    expect(html).toContain("Relationship graph diagram");
    expect(html).toContain("DBS PTE. LTD.");
    expect(html).toContain("Registered Address");
    expect(html).toContain("NO_INFERRED_OWNERSHIP_OR_CONTROL");
  });
});
