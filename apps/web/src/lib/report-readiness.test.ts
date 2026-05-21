import { describe, expect, it } from "vitest";

import { buildReportReadinessChecklist, reportReadinessSummary } from "@/lib/report-readiness";
import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BusinessDossier } from "@/types/dossier";

const dossier: BusinessDossier = {
  analystFollowUps: [{
    action: "Confirm the ACRA identity source rows.",
    category: "identity_confidence",
    evidenceBasis: [{ detail: "No exact match.", kind: "source_gap", ref: "gap.NO_EXACT_MATCH", source: "NO_EXACT_MATCH" }],
    id: "critical-identity",
    priority: "critical",
    reason: "No exact match.",
    whyThisMatters: "Identity confidence affects report quality.",
  }],
  evidence: [],
  freshness: [],
  gaps: [],
  limits: [],
  matchConfidence: [{ confidence: "name-fuzzy", matchedOn: "entityName", source: "ACRA" }],
  provenance: [],
  records: {},
  sourceCoverage: [{
    authRequired: true,
    coverageLevel: "none",
    family: "opencorporates",
    label: "OpenCorporates cross-links",
    reason: "OpenCorporates token is not configured.",
    recordCount: 0,
    status: "credential_blocked",
    tools: ["sg_opencorporates_links"],
  }],
  summary: [],
  title: "Business Dossier",
};

const memo: AnalystMemoReady = {
  citations: [],
  configured: true,
  decisionAid: {
    confidenceBlockers: [],
    nextSteps: [],
    nonAdvisoryReminder: "Operational review only.",
  },
  evidenceMemo: [{ citationIds: [], text: "Uncited generated finding." }],
  gaps: [],
  generatedAt: "2026-05-21T00:00:00.000Z",
  limits: [],
  model: "gpt-4o",
  provider: "openai",
  rejectedClaims: [{ claim: "Unsupported claim", reason: "No source citation." }],
  riskRating: {
    citationIds: [],
    confidenceBlockers: [],
    level: "unknown",
    rationale: "No cited rationale.",
  },
  status: "ready",
};

describe("report readiness checklist", () => {
  it("warns on critical follow-ups, weak identity confidence, unavailable sources, and uncited claims", () => {
    const checklist = buildReportReadinessChecklist({ analystMemo: memo, dossier });

    expect(checklist).toEqual([
      expect.objectContaining({ id: "critical_followups", status: "warning" }),
      expect.objectContaining({ id: "identity_confidence", status: "warning" }),
      expect.objectContaining({ id: "source_availability", status: "warning" }),
      expect.objectContaining({ id: "claim_citations", status: "warning" }),
    ]);
    expect(reportReadinessSummary(checklist)).toContain("readiness warnings");
    expect(reportReadinessSummary(checklist)).toContain("not a pass/fail decision");
  });

  it("keeps clear checklist rows without making a clearance claim", () => {
    const readyDossier: BusinessDossier = {
      ...dossier,
      analystFollowUps: [],
      matchConfidence: [{ confidence: "exact", matchedOn: "uen", source: "ACRA" }],
      sourceCoverage: [],
    };
    const readyMemo: AnalystMemoReady = {
      ...memo,
      citations: [{ id: "c1", label: "ACRA", source: "ACRA", text: "Source fact." }],
      evidenceMemo: [{ citationIds: ["c1"], text: "Cited finding." }],
      rejectedClaims: [],
      riskRating: { ...memo.riskRating, citationIds: ["c1"] },
    };
    const checklist = buildReportReadinessChecklist({ analystMemo: readyMemo, dossier: readyDossier });

    expect(checklist.every((item) => item.status === "ok")).toBe(true);
    expect(reportReadinessSummary(checklist)).toContain("not a clearance or approval decision");
  });
});
