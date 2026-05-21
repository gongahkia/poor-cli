import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BusinessDossier } from "@/types/dossier";

export type ReportSectionId =
  | "review_metadata"
  | "readiness_checklist"
  | "executive_summary"
  | "coverage_matrix"
  | "risk_assessment"
  | "action_plan"
  | "identity_snapshot"
  | "evidence_records"
  | "supplemental_discovery"
  | "gaps"
  | "provenance"
  | "freshness"
  | "limits"
  | "manifest";

export type ReportWritingStyle =
  | "concise_analyst"
  | "audit_ready_formal"
  | "client_friendly_neutral"
  | "internal_escalation";

export type ReportExportFormat = "pdf" | "docx";

export type ReportReviewerMetadata = {
  preparedBy: string;
  reviewedBy: string;
  reviewDate: string;
  caseStatus: string;
  internalReference: string;
  reportPurpose: string;
};

export type ReportTemplate = {
  id: string;
  name: string;
  writingStyle: ReportWritingStyle;
  sections: ReportSectionId[];
  metadata: ReportReviewerMetadata;
};

export type ReportDocumentModel = {
  dossier: BusinessDossier;
  generatedAt: string;
  memo?: AnalystMemoReady;
  template: ReportTemplate;
};

export const REPORT_SECTION_LABELS: Record<ReportSectionId, string> = {
  action_plan: "Action plan",
  coverage_matrix: "Source coverage",
  evidence_records: "Raw evidence appendix",
  executive_summary: "Executive summary",
  freshness: "Freshness",
  gaps: "Gaps and blockers",
  identity_snapshot: "Identity snapshot",
  limits: "Limits",
  manifest: "Audit manifest appendix",
  provenance: "Source attribution",
  readiness_checklist: "Report readiness checklist",
  review_metadata: "Review metadata",
  risk_assessment: "Risk and confidence",
  supplemental_discovery: "Supplemental evidence review",
};

export const REPORT_SECTION_DESCRIPTIONS: Record<ReportSectionId, string> = {
  action_plan: "Operational next checks and confidence blockers.",
  coverage_matrix: "Source families checked, skipped, blocked, unavailable, or not applicable.",
  evidence_records: "Raw matched registry, sector-module, and supplemental records for appendix review.",
  executive_summary: "CDD findings written from cited evidence.",
  freshness: "When Dude observed the evidence and upstream timestamps.",
  gaps: "Missing, stale, skipped, or failed evidence.",
  identity_snapshot: "UEN, status, SSIC, address, and matched modules.",
  limits: "Non-advice and public-data boundaries.",
  manifest: "Hash, signature, schema, source-use warnings, and export metadata.",
  provenance: "Official source coverage and attribution.",
  readiness_checklist: "Warnings for unresolved follow-ups, identity confidence, unavailable sources, and uncited claims.",
  review_metadata: "Prepared-by, reviewed-by, review date, case status, internal reference, and report purpose.",
  risk_assessment: "Risk flags, memo risk rating, and match confidence.",
  supplemental_discovery: "Web, provider, sanctions/media, OpenCorporates, and graph evidence with caveats.",
};

export const REPORT_WRITING_STYLE_LABELS: Record<ReportWritingStyle, string> = {
  audit_ready_formal: "Audit-ready formal",
  client_friendly_neutral: "Client-friendly neutral",
  concise_analyst: "Concise analyst",
  internal_escalation: "Internal escalation",
};

export const REPORT_WRITING_STYLE_DESCRIPTIONS: Record<ReportWritingStyle, string> = {
  audit_ready_formal: "Formal handoff wording with full caveats, source-use warnings, and appendix discipline.",
  client_friendly_neutral: "Plain neutral wording that separates source facts from analyst notes for non-technical readers.",
  concise_analyst: "Short evidence-led wording for internal triage and fast reviewer scanning.",
  internal_escalation: "Blocker-first wording for unresolved risks, failed sources, and exact next actions.",
};

export const DEFAULT_REVIEWER_METADATA: ReportReviewerMetadata = {
  caseStatus: "Draft analyst review",
  internalReference: "",
  preparedBy: "",
  reportPurpose: "CDD analyst handoff",
  reviewDate: "",
  reviewedBy: "",
};

export const DEFAULT_REPORT_SECTIONS: ReportSectionId[] = [
  "review_metadata",
  "readiness_checklist",
  "executive_summary",
  "coverage_matrix",
  "risk_assessment",
  "action_plan",
  "identity_snapshot",
  "evidence_records",
  "supplemental_discovery",
  "gaps",
  "provenance",
  "freshness",
  "limits",
  "manifest",
];

export const DEFAULT_REPORT_TEMPLATE: ReportTemplate = {
  id: "cdd-standard",
  name: "CDD review report",
  metadata: DEFAULT_REVIEWER_METADATA,
  sections: DEFAULT_REPORT_SECTIONS,
  writingStyle: "concise_analyst",
};

export type ReportSectionPresetId =
  | "cdd_intake"
  | "vendor_onboarding"
  | "sector_review"
  | "audit_appendix"
  | "supplemental_evidence_review";

export type ReportSectionPreset = {
  id: ReportSectionPresetId;
  name: string;
  description: string;
  sections: ReportSectionId[];
  writingStyle: ReportWritingStyle;
};

export const REPORT_SECTION_PRESETS: ReportSectionPreset[] = [
  {
    description: "Identity, source coverage, readiness warnings, and immediate follow-ups for opening a CDD file.",
    id: "cdd_intake",
    name: "CDD intake",
    sections: [
      "review_metadata",
      "readiness_checklist",
      "identity_snapshot",
      "coverage_matrix",
      "gaps",
      "action_plan",
      "manifest",
    ],
    writingStyle: "concise_analyst",
  },
  {
    description: "Balanced onboarding packet with cited summary, risk notes, gaps, and source appendices.",
    id: "vendor_onboarding",
    name: "Vendor onboarding",
    sections: [
      "review_metadata",
      "readiness_checklist",
      "executive_summary",
      "identity_snapshot",
      "risk_assessment",
      "coverage_matrix",
      "action_plan",
      "supplemental_discovery",
      "gaps",
      "provenance",
      "freshness",
      "limits",
      "manifest",
    ],
    writingStyle: "client_friendly_neutral",
  },
  {
    description: "Sector-module review with retained-tool rationale, identifiers, evidence records, and gaps.",
    id: "sector_review",
    name: "Sector review",
    sections: [
      "review_metadata",
      "readiness_checklist",
      "executive_summary",
      "coverage_matrix",
      "identity_snapshot",
      "evidence_records",
      "supplemental_discovery",
      "gaps",
      "action_plan",
      "provenance",
      "freshness",
      "limits",
      "manifest",
    ],
    writingStyle: "audit_ready_formal",
  },
  {
    description: "Appendix-first bundle for audit handoff, raw evidence review, and export integrity checks.",
    id: "audit_appendix",
    name: "Audit appendix",
    sections: [
      "review_metadata",
      "readiness_checklist",
      "provenance",
      "freshness",
      "limits",
      "gaps",
      "evidence_records",
      "supplemental_discovery",
      "manifest",
    ],
    writingStyle: "audit_ready_formal",
  },
  {
    description: "Focused supplemental evidence review with provider states, caveats, provenance, and next actions.",
    id: "supplemental_evidence_review",
    name: "Supplemental evidence review",
    sections: [
      "review_metadata",
      "readiness_checklist",
      "supplemental_discovery",
      "action_plan",
      "gaps",
      "provenance",
      "freshness",
      "limits",
      "manifest",
    ],
    writingStyle: "internal_escalation",
  },
];

export function applyReportSectionPreset(
  template: ReportTemplate,
  presetId: ReportSectionPresetId,
): ReportTemplate {
  const preset = REPORT_SECTION_PRESETS.find((item) => item.id === presetId);
  if (preset === undefined) return template;
  return {
    ...template,
    id: preset.id,
    name: preset.name,
    sections: preset.sections,
    writingStyle: preset.writingStyle,
  };
}

export function updateReportReviewerMetadata(
  template: ReportTemplate,
  update: Partial<ReportReviewerMetadata>,
): ReportTemplate {
  return {
    ...template,
    metadata: {
      ...template.metadata,
      ...update,
    },
  };
}

export function getReportReviewerMetadata(template: ReportTemplate): ReportReviewerMetadata {
  return {
    ...DEFAULT_REVIEWER_METADATA,
    ...template.metadata,
  };
}

export function reviewerMetadataRows(metadata: ReportReviewerMetadata): { label: string; value: string }[] {
  return [
    { label: "Prepared by", value: metadata.preparedBy.trim() || "Not provided" },
    { label: "Reviewed by", value: metadata.reviewedBy.trim() || "Not provided" },
    { label: "Review date", value: metadata.reviewDate.trim() || "Not provided" },
    { label: "Case status", value: metadata.caseStatus.trim() || "Not provided" },
    { label: "Internal reference", value: metadata.internalReference.trim() || "Not provided" },
    { label: "Report purpose", value: metadata.reportPurpose.trim() || "Not provided" },
  ];
}

export function moveReportSection(
  sections: readonly ReportSectionId[],
  section: ReportSectionId,
  direction: "up" | "down",
): ReportSectionId[] {
  const next = [...sections];
  const index = next.indexOf(section);
  if (index === -1) return next;
  const swapIndex = direction === "up" ? index - 1 : index + 1;
  if (swapIndex < 0 || swapIndex >= next.length) return next;
  [next[index], next[swapIndex]] = [next[swapIndex]!, next[index]!];
  return next;
}

export function toggleReportSection(
  sections: readonly ReportSectionId[],
  section: ReportSectionId,
): ReportSectionId[] {
  if (section === "executive_summary") {
    return [...sections];
  }
  return sections.includes(section)
    ? sections.filter((item) => item !== section)
    : [...sections, section];
}

export function getReportStyleInstruction(style: ReportWritingStyle): string {
  switch (style) {
    case "audit_ready_formal":
      return "Write formally for an audit-ready CDD file. Keep caveats and source limits explicit.";
    case "client_friendly_neutral":
      return "Write in plain neutral language suitable for a client-facing review packet.";
    case "internal_escalation":
      return "Write for internal escalation. Prioritize blockers, risk flags, and exact next actions.";
    case "concise_analyst":
    default:
      return "Write concise analyst notes. Prefer short evidence-backed statements and no unsupported commentary.";
  }
}
