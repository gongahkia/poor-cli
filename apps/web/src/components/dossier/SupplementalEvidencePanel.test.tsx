import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SupplementalEvidencePanel } from "@/components/dossier/SupplementalEvidencePanel";
import type { BusinessDossier } from "@/types/dossier";

const dossier = {
  evidence: [],
  freshness: [],
  gaps: [],
  limits: [],
  provenance: [],
  records: {
    externalDiligence: [
      {
        title: "Sanctions Screen",
        summary: [{ label: "Candidate matches", value: 1, source: "OpenSanctions" }],
        gaps: [],
        limits: [{ code: "CANDIDATE_SCREEN_ONLY", message: "Candidate screen only." }],
      },
      {
        title: "Adverse Media Lite",
        summary: [{ label: "Feed items matched", value: 0, source: "Official feeds" }],
        gaps: [{ code: "GOV_FEED_UNAVAILABLE", message: "Official public feed returned HTTP 500." }],
        limits: [],
      },
      {
        title: "Relationship Graph",
        summary: [
          { label: "Source-declared edges", value: 1, source: "Graph builder" },
          { label: "Inferred ownership/control edges", value: 0, source: "Graph builder" },
        ],
        gaps: [],
        limits: [{ code: "NO_INFERRED_OWNERSHIP_OR_CONTROL", message: "No ownership/control inference." }],
      },
    ],
  },
  sourceCoverage: [
    {
      authRequired: true,
      coverageLevel: "partial",
      family: "opensanctions",
      label: "OpenSanctions candidate screening",
      reason: "OpenSanctions returned one candidate.",
      recordCount: 1,
      status: "checked",
      tools: ["sg_sanctions_screen"],
    },
    {
      authRequired: true,
      coverageLevel: "none",
      family: "opencorporates",
      gapCodes: ["OPENCORPORATES_API_TOKEN_REQUIRED"],
      label: "OpenCorporates cross-links",
      reason: "OpenCorporates API token is required.",
      recordCount: 0,
      requiredCredentials: ["OPENCORPORATES_API_TOKEN"],
      status: "credential_blocked",
      tools: ["sg_opencorporates_links"],
    },
    {
      authRequired: false,
      coverageLevel: "none",
      family: "adverse_media_lite",
      gapCodes: ["GOV_FEED_UNAVAILABLE"],
      label: "Adverse-media lite",
      reason: "Official public feed returned HTTP 500.",
      recordCount: 0,
      status: "unavailable",
      tools: ["sg_adverse_media_lite"],
    },
    {
      authRequired: false,
      coverageLevel: "partial",
      family: "relationship_graph",
      label: "Relationship graph",
      reason: "Graph built from supplied source-declared links.",
      recordCount: 1,
      status: "checked",
      tools: ["sg_relationship_graph"],
    },
  ],
  summary: [],
  title: "ACME PTE LTD",
} satisfies BusinessDossier;

describe("SupplementalEvidencePanel", () => {
  it("renders supplemental evidence states with caveats and source-use labels", () => {
    const html = renderToStaticMarkup(
      <SupplementalEvidencePanel
        dossier={dossier}
        peopleDiscovery={{
          configured: true,
          entityName: "ACME PTE LTD",
          limits: ["Candidate people references are not verified employees."],
          query: "ACME PTE LTD leadership",
          results: [],
          suggestedActions: [],
          uen: "202400001A",
        }}
        webPresence={{
          configured: true,
          limits: [],
          possibleOfficialWebsite: null,
          query: "ACME PTE LTD",
          results: [],
        }}
      />,
    );

    expect(html).toContain("Supplemental evidence");
    expect(html).toContain("Analyst-review checks");
    expect(html).toContain("Not official registry fact");
    expect(html).toContain("Analyst-review only");
    expect(html).toContain("Candidate result");
    expect(html).toContain("No result");
    expect(html).toContain("Unconfigured");
    expect(html).toContain("Error");
    expect(html).toContain("Provider credentials, plan terms");
    expect(html).toContain("does not infer beneficial ownership or control");
    expect(html).toContain("not sanctions clearance");
  });
});
