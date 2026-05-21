import { describe, expect, it } from "vitest";

import {
  buildReportManifestRows,
  buildReportMetadataRows,
  buildReportReadinessRows,
} from "@/lib/report-export-content";
import { buildDossierExportManifest } from "@/lib/export/manifest";
import { DEFAULT_REPORT_TEMPLATE, updateReportReviewerMetadata } from "@/lib/report-template";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  analystFollowUps: [{
    action: "Review source coverage before handoff.",
    category: "source_unavailable",
    evidenceBasis: [{ detail: "Provider unavailable.", kind: "source_gap", ref: "sourceCoverage.opensanctions", source: "OpenSanctions" }],
    id: "critical-source",
    priority: "critical",
    reason: "OpenSanctions unavailable.",
    whyThisMatters: "Supplemental coverage is blocked.",
  }],
  evidence: [{ label: "ACRA matches", source: "ACRA", value: 1 }],
  freshness: [{ observedAt: "2026-05-21T00:00:00.000Z", source: "ACRA" }],
  gaps: [],
  limits: [{ code: "PUBLIC_DATA_ONLY", message: "Public records only." }],
  matchConfidence: [{ confidence: "exact", matchedOn: "uen", source: "ACRA" }],
  provenance: [{ authRequired: false, coverage: "Identity", recordCount: 1, source: "ACRA", tool: "sg_acra_entities" }],
  records: { acra: [{ entityName: "ACME PTE LTD", uen: "202400001A" }] },
  sourceCoverage: [{
    authRequired: false,
    coverageLevel: "full",
    family: "acra",
    label: "ACRA entity identity",
    reason: "ACRA lookup returned one source row.",
    recordCount: 1,
    status: "checked",
    tools: ["sg_acra_entities"],
  }],
  summary: [{ label: "UEN", source: "ACRA", value: "202400001A" }],
  title: "ACME PTE LTD",
};

describe("report export content", () => {
  it("builds shared PDF/DOCX metadata rows from reviewer fields and writing style", () => {
    const template = updateReportReviewerMetadata(DEFAULT_REPORT_TEMPLATE, {
      caseStatus: "Pending reviewer sign-off",
      internalReference: "CDD-2026-001",
      preparedBy: "Analyst A",
      reportPurpose: "Vendor onboarding review",
      reviewDate: "2026-05-21",
      reviewedBy: "Reviewer B",
    });

    expect(buildReportMetadataRows(template)).toEqual(expect.arrayContaining([
      { label: "Prepared by", value: "Analyst A" },
      { label: "Reviewed by", value: "Reviewer B" },
      { label: "Internal reference", value: "CDD-2026-001" },
      { label: "Report purpose", value: "Vendor onboarding review" },
      { label: "Report style", value: "Concise analyst" },
    ]));
  });

  it("builds readiness rows and manifest rows without dropping manifest evidence fields", async () => {
    const manifest = await buildDossierExportManifest({
      dossier,
      generatedAt: "2026-05-21T00:00:00.000Z",
      reportTemplate: DEFAULT_REPORT_TEMPLATE,
    });

    expect(buildReportReadinessRows(dossier, undefined)).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "Readiness summary", value: expect.stringContaining("readiness warning") }),
      expect.objectContaining({ label: "Warning - Unresolved critical follow-ups" }),
      expect.objectContaining({ label: "Warning - Uncited claims" }),
    ]));
    expect(buildReportManifestRows(manifest)).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "Manifest schema", value: "dude-export-manifest/v1" }),
      expect.objectContaining({ label: "Dossier hash", value: expect.any(String) }),
      expect.objectContaining({ label: "Source-use warnings", value: expect.stringContaining("ACRA source-use review required") }),
      expect.objectContaining({ label: "Source coverage", value: expect.stringContaining("ACRA entity identity: checked/full") }),
      expect.objectContaining({ label: "Readiness warnings", value: expect.stringContaining("Unresolved critical follow-ups") }),
    ]));
    expect(manifest.provenance).toEqual([{ source: "ACRA", tool: "sg_acra_entities", recordCount: 1 }]);
    expect(manifest.sourceFreshness).toEqual([{ source: "ACRA", observedAt: "2026-05-21T00:00:00.000Z" }]);
    expect(manifest.sourceCoverage).toEqual([expect.objectContaining({ family: "acra", status: "checked" })]);
  });
});
