import { describe, expect, it } from "vitest";

import {
  buildDossierExportManifest,
  verifyDossierExportManifest,
} from "@/lib/export/manifest";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  evidence: [{ label: "ACRA matches", source: "ACRA", value: 1 }],
  freshness: [{ source: "ACRA", observedAt: "2026-05-17T00:00:00Z", upstreamTimestamp: null }],
  gaps: [],
  limits: [{ code: "PUBLIC_DATA_ONLY", message: "Public records only." }],
  analystFollowUps: [{
    action: "Record source coverage limitation before export.",
    category: "report_quality",
    evidenceBasis: [{ detail: "Public records only.", kind: "evidence_limitation", ref: "limit.PUBLIC_DATA_ONLY", source: "Dossier limit" }],
    id: "follow-up-01-optional-report-quality-limit-public-data-only",
    priority: "optional",
    reason: "PUBLIC_DATA_ONLY: Public records only.",
    whyThisMatters: "Report readers need the same evidence boundaries.",
  }],
  provenance: [{ authRequired: false, coverage: "Registry", recordCount: 1, source: "ACRA", tool: "sg_acra_entities" }],
  records: { acra: [{ entityName: "DBS BANK LTD", uen: "03591300B" }] },
  sourceCoverage: [{
    authRequired: false,
    coverageLevel: "full",
    family: "acra",
    label: "ACRA entity identity",
    reason: "ACRA lookup ran and returned one public record.",
    recordCount: 1,
    status: "checked",
    tools: ["sg_acra_entities"],
  }],
  summary: [{ label: "UEN", value: "03591300B" }],
  title: "Business Dossier",
};

describe("export manifest", () => {
  it("creates stable dossier hashes and verifies them", async () => {
    const generatedAt = "2026-05-17T00:00:00Z";
    const first = await buildDossierExportManifest({ dossier, generatedAt });
    const second = await buildDossierExportManifest({ dossier, generatedAt });

    expect(first.schemaVersion).toBe("dude-export-manifest/v1");
    expect(first.dossierHash).toBe(second.dossierHash);
    expect(first.signature.value).toBe(second.signature.value);
    expect(first.sourceUseWarnings).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: "acra_source_use",
        message: expect.stringContaining("hosted paid redistribution"),
      }),
    ]));
    expect(first.sourceCoverage).toEqual([
      expect.objectContaining({ family: "acra", status: "checked", coverageLevel: "full" }),
    ]);
    expect(first.analystFollowUps).toEqual([
      expect.objectContaining({
        category: "report_quality",
        evidenceRefs: ["limit.PUBLIC_DATA_ONLY"],
        priority: "optional",
      }),
    ]);
    await expect(verifyDossierExportManifest({ dossier, manifest: first })).resolves.toBe(true);
  });

  it("includes compact orchestrator trace metadata when supplied", async () => {
    const manifest = await buildDossierExportManifest({
      dossier,
      generatedAt: "2026-05-17T00:00:00Z",
      orchestration: {
        acraSectorHints: [],
        effectiveSectorHints: [],
        officialModules: ["acra"],
        reranDossierForWebSectorHints: false,
        stages: [{
          detail: "Canonical entity resolved.",
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
      },
    });

    expect(manifest.includedArtifacts.orchestrationTrace).toBe(true);
    expect(manifest.orchestration).toMatchObject({
      status: "ready",
      stages: [{ id: "acra_identity", status: "completed" }],
    });
  });
});
