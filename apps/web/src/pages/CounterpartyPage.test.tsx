import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(new URL("./CounterpartyPage.tsx", import.meta.url), "utf8");

describe("CounterpartyPage CDD case workflow", () => {
  it("keeps the REST gateway resolver and CDD orchestrator integration", () => {
    expect(source).toContain("/api/v1/dude/resolve-counterparty");
    expect(source).toContain("/api/v1/dude/cdd-orchestrator");
    expect(source).toContain("confirmedCandidate");
    expect(source).not.toContain("callTool<BusinessDossier>");
    expect(source).not.toContain("sg_business_dossier");
  });

  it("renders raw CDD evidence sections and case workflow affordances", () => {
    expect(source).toContain("Case workflow");
    expect(source).toContain("Case status");
    expect(source).toContain("Review notes");
    expect(source).toContain("Follow-up tasks");
    expect(source).toContain("Report readiness");
    expect(source).toContain("Export case JSON");
    expect(source).toContain("Entity identity");
    expect(source).toContain("Source-backed summary");
    expect(source).toContain("Confidence blockers");
    expect(source).toContain("Analyst follow-ups");
    expect(source).toContain("Evidence records");
    expect(source).toContain("Sector workflow guide");
    expect(source).toContain("Sector module status");
    expect(source).toContain("Provenance and freshness");
    expect(source).toContain("Gaps and limits");
    expect(source).toContain("Raw orchestrator response");
    expect(source).not.toContain("DossierFindingsTabs");
    expect(source).not.toContain("DossierActionButton");
  });

  it("preserves CDD safety language and simple PDF/DOCX export controls", () => {
    expect(source).toContain("No clearance is implied");
    expect(source).toContain("imply approval, rejection, compliance clearance");
    expect(source).toContain("Absence of public evidence is not a positive");
    expect(source).toContain("exportDossierPdf");
    expect(source).toContain("exportDossierDocx");
    expect(source).toContain("REPORT_WRITING_STYLE_LABELS");
  });
});
