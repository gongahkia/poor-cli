import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EvidenceSection } from "@/components/dossier/EvidenceSection";
import { GapsSection } from "@/components/dossier/GapsSection";
import { HandoffSection } from "@/components/dossier/HandoffSection";
import { PdpaChecklistSection } from "@/components/dossier/PdpaChecklistSection";
import { RiskSection } from "@/components/dossier/RiskSection";
import { SnapshotSection } from "@/components/dossier/SnapshotSection";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  evidence: [{ label: "ACRA matches", source: "ACRA", value: 1 }],
  freshness: [],
  gaps: [],
  limits: [],
  provenance: [],
  records: {
    acra: [{
      buildingName: "Marina Bay Financial Centre",
      entityName: "DBS BANK LTD",
      postalCode: "018982",
      streetName: "Marina Boulevard",
      uen: "03591300B",
    }],
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

  it("renders a map link from the snapshot address", () => {
    const html = renderToStaticMarkup(<SnapshotSection dossier={dossier} />);
    expect(html).toContain("Location");
    expect(html).toContain("https://www.google.com/maps/search/?api=1");
    expect(html).toContain("https://www.google.com/maps?q=");
    expect(html).toContain("Map is based on the address returned in the dossier");
  });

  it("renders snapshot confidence as a score-bound pill instead of a field card", () => {
    const html = renderToStaticMarkup(<SnapshotSection dossier={{
      ...dossier,
      records: {
        ...dossier.records,
        quality: {
          dossierConfidence: {
            level: "high",
            score: 0.92,
          },
        },
      },
    }} />);

    expect(html).toContain("Confidence: high (92%)");
    expect(html).toContain("bg-emerald-50");
    expect(html).not.toContain(">Confidence</dt>");
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

  it("renders risk codes as readable labels", () => {
    const html = renderToStaticMarkup(<RiskSection dossier={{
      ...dossier,
      riskFlags: [{
        code: "ENTITY_NOT_ACTIVE",
        message: "Entity status is not live.",
        severity: "high",
        source: "ACRA",
      }],
    }} />);

    expect(html).toContain("Entity not active");
    expect(html).toContain("ACRA");
    expect(html).not.toContain(">ENTITY_NOT_ACTIVE");
  });

  it("renders the agent handoff as a collapsed copy artifact", () => {
    const html = renderToStaticMarkup(<HandoffSection dossier={{
      ...dossier,
      records: {
        ...dossier.records,
        handoff: {
          markdown: "Due Diligence Handoff\nRaw handoff body",
        },
      },
      nextChecks: [{
        input: { uen: "197700546G" },
        reason: "Retrieve full ACRA entity details for deeper officer and status inspection.",
        tool: "sg_acra_entities",
      }],
      riskFlags: [{
        code: "ENTITY_NOT_ACTIVE",
        message: "Entity status is not live.",
        severity: "high",
        source: "ACRA",
      }],
    }} />);

    expect(html).toContain("Agent handoff");
    expect(html).toContain("Copy a structured summary for another analyst or agent.");
    expect(html).toContain("Copy handoff");
    expect(html).not.toContain("Raw handoff body");
  });

  it("renders the PDPA checklist with analyst actions and export affordance", () => {
    const html = renderToStaticMarkup(<PdpaChecklistSection dossier={dossier} onExportReport={() => undefined} />);
    expect(html).toContain("PDPA vendor diligence");
    expect(html).toContain("Section 24 / Protection Obligation");
    expect(html).toContain("Section 26 / Transfer Limitation Obligation");
    expect(html).toContain("Export PDPA report");
  });
});
