import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AnalystMemoSection } from "@/components/dossier/AnalystMemoSection";
import { DossierHeaderLogo } from "@/components/dossier/DossierHeaderLogo";
import { DossierFindingsTabs } from "@/components/dossier/DossierFindingsTabs";
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
  it("renders a known company logo in the dossier header", () => {
    const html = renderToStaticMarkup(<DossierHeaderLogo dossier={{
      ...dossier,
      summary: [{ label: "Entity", source: "ACRA", value: "DBS FINANCE NOMINEES PTE LTD" }],
    }} />);

    expect(html).toContain("alt=\"DBS logo\"");
    expect(html).toContain("https://logos-world.net/wp-content/uploads/2023/04/DBS-Logo.png");
    expect(html).toContain("DBS FINANCE NOMINEES PTE LTD brand mark");
  });

  it("falls back to initials when no known company logo is mapped", () => {
    const html = renderToStaticMarkup(<DossierHeaderLogo dossier={{
      ...dossier,
      summary: [{ label: "Entity", source: "ACRA", value: "Example Trading Pte Ltd" }],
    }} />);

    expect(html).toContain("ET");
    expect(html).not.toContain("<img");
  });

  it("renders success evidence rows", () => {
    const html = renderToStaticMarkup(<EvidenceSection dossier={dossier} />);
    expect(html).toContain("DBS BANK LTD");
    expect(html).toContain("Matched");
  });

  it("renders a map link from the snapshot address", () => {
    const html = renderToStaticMarkup(<SnapshotSection dossier={dossier} />);
    expect(html).toContain("Location");
    expect(html).not.toContain(">Address</dt>");
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

    const emptyGapHtml = renderToStaticMarkup(<GapsSection dossier={{ ...dossier, gaps: [] }} />);
    expect(emptyGapHtml).toBe("");
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
    expect(html).toContain("Run all available checks");
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

  it("renders the summary-first report shell with evidence pack sections", () => {
    const html = renderToStaticMarkup(
      <DossierFindingsTabs
        dossier={{
          ...dossier,
          nextChecks: [{
            input: { uen: "197700546G" },
            reason: "Retrieve full ACRA entity details for deeper officer and status inspection.",
            tool: "sg_acra_entities",
          }],
        }}
        isPdpaExporting={false}
        memoState={{
          status: "unavailable",
          memo: {
            configured: false,
            gaps: [],
            generatedAt: "2026-05-17T14:56:00.000Z",
            limits: [],
            model: "gpt-4o",
            provider: "openai",
            reason: {
              code: "not_configured",
              message: "OpenAI key not configured.",
            },
            status: "unavailable",
          },
        }}
        onExportPdpaReport={() => undefined}
        onModuleFollowUp={() => undefined}
        orchestration={{
          acraSectorHints: [],
          effectiveSectorHints: [],
          officialModules: ["acra"],
          reranDossierForWebSectorHints: false,
          stages: [{
            detail: "Canonical entity resolved through ACRA before downstream CDD enrichment.",
            id: "acra_identity",
            label: "ACRA identity lookup",
            status: "completed",
            tools: ["sg_acra_entities"],
          }],
          status: "ready",
          strategy: "acra_then_sector_then_supplemental_memo",
          supplementalTools: ["sg_relationship_graph"],
          limits: [],
          webSectorHints: [],
        }}
        peopleDiscoveryState={{ status: "error", message: "No people results." }}
        rerunningModule={null}
        sharedMemoState={null}
        webPresenceState={{ status: "error", message: "No web results." }}
      />,
    );

    expect(html).toContain("CDD Summary");
    expect(html).toContain("Summary");
    expect(html).toContain("Evidence Pack");
    expect(html).toContain("Report Builder");
    expect(html).not.toContain("CDD orchestrator trace");
    expect(html).not.toContain("ACRA identity lookup");
    expect(html).not.toContain("What To Check Next");
    expect(html).not.toContain("Agent handoff");
    expect(html).not.toContain("Overview");
    expect(html).not.toContain("What we couldn&#x27;t find");
    expect(html).not.toContain("data-[state=active]");
  });

  it("keeps evidence pack details off the default summary tab", () => {
    const html = renderToStaticMarkup(
      <DossierFindingsTabs
        dossier={{
          ...dossier,
          gaps: [{ code: "GEBIZ_NO_MATCH", message: "No GeBIZ awards returned." }],
        }}
        isPdpaExporting={false}
        memoState={{
          status: "unavailable",
          memo: {
            configured: false,
            gaps: [],
            generatedAt: "2026-05-17T14:56:00.000Z",
            limits: [],
            model: "gpt-4o",
            provider: "openai",
            reason: {
              code: "not_configured",
              message: "OpenAI key not configured.",
            },
            status: "unavailable",
          },
        }}
        onExportPdpaReport={() => undefined}
        onModuleFollowUp={() => undefined}
        peopleDiscoveryState={{ status: "error", message: "No people results." }}
        rerunningModule={null}
        sharedMemoState={null}
        webPresenceState={{ status: "error", message: "No web results." }}
      />,
    );

    expect(html).toContain("Evidence Pack");
    expect(html).not.toContain("What we couldn&#x27;t find");
    expect(html).not.toContain("GEBIZ_NO_MATCH");
    expect(html).not.toContain("lg:grid-cols-6");
  });

  it("renders a human-readable executive overview with clickable evidence-backed facts", () => {
    const html = renderToStaticMarkup(
      <DossierFindingsTabs
        dossier={{
          ...dossier,
          gaps: [{
            code: "OPENSANCTIONS_UNAVAILABLE",
            message: "OpenSanctions screening requires OPENSANCTIONS_API_KEY.",
          }],
          records: {
            ...dossier.records,
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
          riskFlags: [{
            code: "ENTITY_NOT_ACTIVE",
            message: "Entity status is not live.",
            severity: "high",
            source: "ACRA",
          }],
          summary: [
            { label: "Entity", source: "ACRA", value: "DBS PTE. LTD." },
            { label: "UEN", source: "ACRA", value: "197700546G" },
            { label: "Entity status", source: "ACRA", value: "Dissolved - Members Voluntary Winding Up" },
          ],
        }}
        isPdpaExporting={false}
        memoState={{
          status: "ready",
          memo: {
            status: "ready",
            configured: true,
            provider: "openai",
            model: "gpt-4o",
            generatedAt: "2026-05-17T14:56:00.000Z",
            evidenceMemo: [{
              text: "Registry status requires analyst review before any new engagement.",
              citationIds: ["summary-3"],
            }],
            riskRating: {
              level: "high",
              rationale: "The entity is not active.",
              citationIds: ["risk-1"],
              confidenceBlockers: ["OpenSanctions API key is not configured."],
            },
            decisionAid: {
              nextSteps: ["Retrieve full ACRA entity details for deeper officer and status inspection."],
              confidenceBlockers: ["OpenSanctions API key is not configured."],
              nonAdvisoryReminder: "Operational follow-up only.",
            },
            citations: [],
            gaps: [],
            limits: [],
            rejectedClaims: [],
          },
        }}
        onExportPdpaReport={() => undefined}
        onModuleFollowUp={() => undefined}
        peopleDiscoveryState={{ status: "error", message: "No people results." }}
        rerunningModule={null}
        sharedMemoState={null}
        webPresenceState={{ status: "error", message: "No web results." }}
      />,
    );

    expect(html).toContain("is an ACRA-matched Singapore entity");
    expect(html).toContain("Dissolved - Members Voluntary Winding Up");
    expect(html).toContain("data-citation-id=\"summary-3\"");
    expect(html).toContain("Supplemental screening is not yet complete");
    expect(html).not.toContain("No sanctions or adverse media were identified");
  });

  it("renders the analyst memo as a formatted note with collapsed references", () => {
    const html = renderToStaticMarkup(
      <AnalystMemoSection
        sharedState="ready"
        state={{
          status: "ready",
          memo: {
            status: "ready",
            configured: true,
            provider: "openai",
            model: "gpt-4o",
            generatedAt: "2026-05-17T14:56:00.000Z",
            evidenceMemo: [{
              text: "Entity: DBS PTE. LTD. is dissolved under Members Voluntary Winding Up.",
              citationIds: ["summary-1", "summary-3"],
            }],
            riskRating: {
              level: "high",
              rationale: "The entity is not active.",
              citationIds: ["risk-1"],
              confidenceBlockers: ["Registry matching is bounded."],
            },
            decisionAid: {
              nextSteps: ["Retrieve full ACRA entity details."],
              confidenceBlockers: ["Registry matching is bounded."],
              nonAdvisoryReminder: "Operational follow-up only.",
            },
            citations: [
              { id: "summary-1", label: "Entity", source: "ACRA", text: "Entity: DBS PTE. LTD." },
              {
                id: "risk-1",
                label: "ENTITY_NOT_ACTIVE",
                source: "ACRA",
                text: "Entity status is not Live or Registered.",
              },
            ],
            gaps: [],
            limits: [],
            rejectedClaims: [],
          },
        }}
      />,
    );

    expect(html).toContain("Evidence-backed findings");
    expect(html).toContain("Action checklist");
    expect(html).toContain("Evidence references (2)");
    expect(html).toContain("Entity Not Active");
    expect(html).not.toContain("<h3 class=\"text-sm font-semibold text-foreground\">Citations</h3>");
  });
});
