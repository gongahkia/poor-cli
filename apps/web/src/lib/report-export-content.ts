import { buildReportReadinessChecklist, reportReadinessSummary } from "@/lib/report-readiness";
import {
  REPORT_WRITING_STYLE_DESCRIPTIONS,
  REPORT_WRITING_STYLE_LABELS,
  getReportReviewerMetadata,
  reviewerMetadataRows,
  type ReportTemplate,
} from "@/lib/report-template";
import type { DossierExportManifest } from "@/lib/export/manifest";
import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BriefArtifact, BriefSummaryItem } from "@/types/dossier";

export function buildReportMetadataRows(template: ReportTemplate): BriefSummaryItem[] {
  return [
    ...reviewerMetadataRows(getReportReviewerMetadata(template)),
    { label: "Report style", value: REPORT_WRITING_STYLE_LABELS[template.writingStyle] },
    { label: "Style intent", value: REPORT_WRITING_STYLE_DESCRIPTIONS[template.writingStyle] },
  ];
}

export function buildReportReadinessRows(
  dossier: BriefArtifact,
  analystMemo: AnalystMemoReady | undefined,
): BriefSummaryItem[] {
  const readiness = buildReportReadinessChecklist({
    dossier,
    ...(analystMemo === undefined ? {} : { analystMemo }),
  });
  return [
    { label: "Readiness summary", value: reportReadinessSummary(readiness) },
    ...readiness.map((item) => ({
      label: `${item.status === "warning" ? "Warning" : "Checked"} - ${item.label}`,
      value: `${item.detail}${item.sourceRefs.length === 0 ? "" : ` Source refs: ${item.sourceRefs.join(", ")}`}`,
    })),
  ];
}

export function buildReportManifestRows(manifest: DossierExportManifest): BriefSummaryItem[] {
  return [
    { label: "Manifest schema", value: manifest.schemaVersion },
    { label: "Dossier hash", value: manifest.dossierHash },
    { label: "Signature", value: `${manifest.signature.algorithm}: ${manifest.signature.value}` },
    { label: "Generated", value: manifest.generatedAt },
    { label: "Tool version", value: manifest.toolVersion },
    { label: "Report template", value: `${manifest.reportTemplate.name}; ${manifest.reportTemplate.writingStyle}; ${manifest.reportTemplate.sections.join(", ")}` },
    { label: "Reviewer metadata", value: reviewerMetadataRows(manifest.reviewerMetadata).map((row) => `${row.label}: ${row.value}`).join("; ") },
    { label: "Readiness warnings", value: manifest.reportReadiness.filter((item) => item.status === "warning").map((item) => item.label).join("; ") || "None generated" },
    { label: "Orchestration status", value: manifest.orchestration?.status ?? "Not included" },
    { label: "Orchestration strategy", value: manifest.orchestration?.strategy ?? "Not included" },
    {
      label: "Orchestration stages",
      value: manifest.orchestration?.stages.map((stage) => `${stage.label}: ${stage.status}`).join("; ") ?? "Not included",
    },
    {
      label: "Source-use warnings",
      value: manifest.sourceUseWarnings.length === 0
        ? "None triggered"
        : manifest.sourceUseWarnings.map((warning) => `${warning.title}: ${warning.triggeredBy.join(", ")}`).join("; "),
    },
    {
      label: "Source coverage",
      value: manifest.sourceCoverage.length === 0
        ? "Not included"
        : manifest.sourceCoverage.map((item) => `${item.label}: ${item.status}/${item.coverageLevel}`).join("; "),
    },
    {
      label: "Analyst follow-ups",
      value: manifest.analystFollowUps.length === 0
        ? "None included"
        : manifest.analystFollowUps.map((item) => `${item.priority}/${item.category}: ${item.action}`).join("; "),
    },
    { label: "Signature note", value: manifest.signature.note },
  ];
}
