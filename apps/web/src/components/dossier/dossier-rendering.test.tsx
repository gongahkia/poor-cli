import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EvidenceSection } from "@/components/dossier/EvidenceSection";
import { GapsSection } from "@/components/dossier/GapsSection";
import { PdpaChecklistSection } from "@/components/dossier/PdpaChecklistSection";
import { RiskSection } from "@/components/dossier/RiskSection";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  evidence: [{ label: "ACRA matches", source: "ACRA", value: 1 }],
  freshness: [],
  gaps: [],
  limits: [],
  provenance: [],
  records: {
    acra: [{ entityName: "DBS BANK LTD", uen: "03591300B" }],
    resolution: {
      matchedModules: ["acra"],
      moduleReasons: [{
        matched: true,
        module: "acra",
        reason: "ACRA matched.",
        searched: true,
        selectedBy: ["default"],
        status: "matched",
      }],
      searchedModules: ["acra"],
    },
  },
  riskFlags: [],
  summary: [],
  title: "Business Dossier",
};

describe("dossier rendering", () => {
  it("renders success evidence rows", () => {
    const html = renderToStaticMarkup(<EvidenceSection dossier={dossier} />);
    expect(html).toContain("DBS BANK LTD");
    expect(html).toContain("Matched");
  });

  it("renders no-match and upstream-gap states", () => {
    const noMatchHtml = renderToStaticMarkup(<EvidenceSection dossier={{
      ...dossier,
      records: {
        resolution: {
          matchedModules: [],
          moduleReasons: [{
            matched: false,
            module: "acra",
            reason: "ACRA returned no match.",
            searched: true,
            selectedBy: ["default"],
            status: "unmatched",
          }],
          searchedModules: ["acra"],
        },
      },
    }} />);
    expect(noMatchHtml).toContain("No official match");
    expect(noMatchHtml).toContain("No matched registry rows to display.");

    const gapHtml = renderToStaticMarkup(<GapsSection dossier={{
      ...dossier,
      gaps: [{ code: "ACRA_UNAVAILABLE", message: "ACRA timed out." }],
    }} />);
    expect(gapHtml).toContain("official source unavailable");
  });

  it("renders actionable follow-ups for skipped sector modules", () => {
    const html = renderToStaticMarkup(<EvidenceSection
      dossier={{
        ...dossier,
        records: {
          resolution: {
            matchedModules: ["acra"],
            moduleReasons: [
              {
                matched: true,
                module: "acra",
                reason: "ACRA matched.",
                searched: true,
                selectedBy: ["default"],
                status: "matched",
              },
              {
                matched: false,
                module: "bca",
                reason: "Skipped because construction context was not selected.",
                searched: false,
                selectedBy: [],
                status: "skipped",
              },
            ],
            searchedModules: ["acra"],
          },
        },
        summary: [{ label: "Entity", value: "DBS BANK LTD" }],
      }}
      onModuleFollowUp={() => undefined}
    />);

    expect(html).toContain("Construction company name or UEN");
    expect(html).toContain("Run BCA follow-up");
  });

  it("renders risk empty state", () => {
    expect(renderToStaticMarkup(<RiskSection dossier={dossier} />)).toContain("No risk flags were returned");
  });

  it("renders the PDPA checklist with analyst actions and export affordance", () => {
    const html = renderToStaticMarkup(<PdpaChecklistSection dossier={dossier} onExportReport={() => undefined} />);
    expect(html).toContain("PDPA vendor diligence");
    expect(html).toContain("Section 24 / Protection Obligation");
    expect(html).toContain("Section 26 / Transfer Limitation Obligation");
    expect(html).toContain("Export PDPA report");
  });
});
