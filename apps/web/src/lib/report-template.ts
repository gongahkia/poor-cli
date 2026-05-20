import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BusinessDossier } from "@/types/dossier";

export type ReportSectionId =
  | "executive_summary"
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

export type ReportTemplate = {
  id: string;
  name: string;
  writingStyle: ReportWritingStyle;
  sections: ReportSectionId[];
};

export type ReportDocumentModel = {
  dossier: BusinessDossier;
  generatedAt: string;
  memo?: AnalystMemoReady;
  template: ReportTemplate;
};

export const REPORT_SECTION_LABELS: Record<ReportSectionId, string> = {
  action_plan: "Action plan",
  evidence_records: "Evidence records",
  executive_summary: "Executive summary",
  freshness: "Freshness",
  gaps: "Gaps and blockers",
  identity_snapshot: "Identity snapshot",
  limits: "Limits",
  manifest: "Export manifest",
  provenance: "Source attribution",
  risk_assessment: "Risk and confidence",
  supplemental_discovery: "Supplemental discovery",
};

export const REPORT_SECTION_DESCRIPTIONS: Record<ReportSectionId, string> = {
  action_plan: "Operational next checks and confidence blockers.",
  evidence_records: "Matched registry and sector-module records.",
  executive_summary: "CDD findings written from cited evidence.",
  freshness: "When Dude observed the evidence and upstream timestamps.",
  gaps: "Missing, stale, skipped, or failed evidence.",
  identity_snapshot: "UEN, status, SSIC, address, and matched modules.",
  limits: "Non-advice and public-data boundaries.",
  manifest: "Hash, signature, schema, and export metadata.",
  provenance: "Official source coverage and attribution.",
  risk_assessment: "Risk flags, memo risk rating, and match confidence.",
  supplemental_discovery: "Web presence and people-discovery hints for analyst review.",
};

export const REPORT_WRITING_STYLE_LABELS: Record<ReportWritingStyle, string> = {
  audit_ready_formal: "Audit-ready formal",
  client_friendly_neutral: "Client-friendly neutral",
  concise_analyst: "Concise analyst",
  internal_escalation: "Internal escalation",
};

export const REPORT_WRITING_STYLE_DESCRIPTIONS: Record<ReportWritingStyle, string> = {
  audit_ready_formal: "Formal language, full caveats, and source discipline for client-file review.",
  client_friendly_neutral: "Plain, neutral phrasing suitable for sharing with non-technical stakeholders.",
  concise_analyst: "Short evidence-led wording for internal triage.",
  internal_escalation: "Sharper blocker and next-action language for high-friction reviews.",
};

export const DEFAULT_REPORT_SECTIONS: ReportSectionId[] = [
  "executive_summary",
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
  sections: DEFAULT_REPORT_SECTIONS,
  writingStyle: "concise_analyst",
};

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
