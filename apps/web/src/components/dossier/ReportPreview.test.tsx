import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ReportPreview } from "@/components/dossier/ReportPreview";
import { DEFAULT_REPORT_TEMPLATE } from "@/lib/report-template";
import type { BusinessDossier } from "@/types/dossier";

const dossier = {
  evidence: [{ label: "ACRA records inspected", source: "ACRA", value: 1 }],
  freshness: [{ observedAt: "2026-05-20T00:00:00.000Z", source: "ACRA" }],
  gaps: [{ code: "OPENCORPORATES_API_TOKEN_REQUIRED", message: "OpenCorporates token is not configured." }],
  limits: [{ code: "NO_LEGAL_ADVICE", message: "Operational review only." }],
  matchConfidence: [{ confidence: "exact", matchedOn: "uen", source: "ACRA" }],
  nextChecks: [{ input: { uen: "197700546G" }, reason: "Retrieve full ACRA entity details.", tool: "sg_acra_entities" }],
  provenance: [{ authRequired: false, coverage: "ACRA identity lookup.", recordCount: 1, source: "ACRA", tool: "sg_acra_entities" }],
  records: {
    acra: [{
      entityName: "DBS PTE. LTD.",
      entityStatusDescription: "Dissolved - Members Voluntary Winding Up",
      entityTypeDescription: "Local Company",
      postalCode: "068809",
      primarySsicCode: "64202",
      streetName: "Shenton Way",
      uen: "197700546G",
    }],
    resolution: { matchedModules: ["acra"], searchedModules: ["acra"] },
  },
  riskFlags: [{ code: "ENTITY_NOT_ACTIVE", message: "Entity is not active.", severity: "high", source: "ACRA" }],
  sourceCoverage: [
    {
      authRequired: false,
      coverageLevel: "full",
      family: "acra",
      label: "ACRA entity identity",
      reason: "ACRA lookup ran and returned one public record.",
      recordCount: 1,
      status: "checked",
      tools: ["sg_acra_entities"],
    },
    {
      authRequired: true,
      coverageLevel: "none",
      family: "opencorporates",
      label: "OpenCorporates cross-links",
      reason: "OpenCorporates credentials are not configured.",
      recordCount: 0,
      status: "credential_blocked",
      tools: ["sg_opencorporates_links"],
    },
  ],
  summary: [
    { label: "Entity", source: "ACRA", value: "DBS PTE. LTD." },
    { label: "UEN", source: "ACRA", value: "197700546G" },
    { label: "Entity status", source: "ACRA", value: "Dissolved - Members Voluntary Winding Up" },
  ],
  title: "DBS PTE. LTD.",
} satisfies BusinessDossier;

describe("ReportPreview", () => {
  it("renders a generated document preview from the selected report template", () => {
    const html = renderToStaticMarkup(
      <ReportPreview
        dossier={dossier}
        memoState={{
          status: "ready",
          memo: {
            citations: [],
            configured: true,
            decisionAid: {
              confidenceBlockers: ["OpenCorporates token is not configured."],
              nextSteps: ["Retrieve full ACRA entity details."],
              nonAdvisoryReminder: "Operational follow-up only.",
            },
            evidenceMemo: [{ citationIds: ["summary-1"], text: "DBS PTE. LTD. is dissolved." }],
            gaps: [],
            generatedAt: "2026-05-20T00:00:00.000Z",
            limits: [],
            model: "gpt-4o",
            provider: "openai",
            rejectedClaims: [],
            riskRating: {
              citationIds: ["risk-1"],
              confidenceBlockers: [],
              level: "high",
              rationale: "The entity is not active.",
            },
            status: "ready",
          },
        }}
        peopleDiscoveryState={{
          status: "success",
          discovery: {
            configured: true,
            entityName: "DBS PTE. LTD.",
            limits: [],
            query: "DBS PTE. LTD. leadership",
            results: [],
            suggestedActions: [],
            uen: "197700546G",
          },
        }}
        template={DEFAULT_REPORT_TEMPLATE}
        webPresenceState={{
          status: "success",
          presence: {
            configured: true,
            limits: [],
            possibleOfficialWebsite: "https://www.dbs.com",
            query: "DBS PTE. LTD.",
            results: [],
          },
        }}
      />,
    );

    expect(html).toContain("Generated document preview");
    expect(html).toContain("Dude CDD review report");
    expect(html).toContain("DBS PTE. LTD.");
    expect(html).toContain("Executive summary");
    expect(html).toContain("Source coverage");
    expect(html).toContain("OpenCorporates cross-links");
    expect(html).toContain("Risk and confidence");
    expect(html).toContain("Export manifest");
    expect(html).toContain("Hash, schema version, signature");
  });

  it("does not render missing coverage as a clean gap state", () => {
    const html = renderToStaticMarkup(
      <ReportPreview
        dossier={{ ...dossier, gaps: [] }}
        memoState={{ status: "error", message: "AI memo unavailable." }}
        peopleDiscoveryState={{ status: "error", message: "People discovery not run." }}
        template={DEFAULT_REPORT_TEMPLATE}
        webPresenceState={{ status: "error", message: "Web presence not run." }}
      />,
    );

    expect(html).toContain("OpenCorporates credentials are not configured.");
    expect(html).not.toContain("No gaps returned.");
  });
});
