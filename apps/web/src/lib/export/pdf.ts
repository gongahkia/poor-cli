import type { jsPDF as JsPdfInstance } from "jspdf";
import {
  buildDiligenceSnapshot,
  confidenceLabel,
  formatTimestamp,
  formatRecordValue,
  getActionableSourceCoverageGaps,
  getDossierRecordGroups,
  getSourceCoverage,
  riskCodeLabel,
  riskSeverityLabel,
  sourceCoverageLevelLabel,
  sourceCoverageStatusLabel,
} from "@/lib/dossier";
import { complianceUseLimitations } from "@/lib/compliance";
import { buildDossierExportManifest } from "@/lib/export/manifest";
import { formatNextCheckInputSummary } from "@/lib/next-checks";
import { DEFAULT_REPORT_TEMPLATE, REPORT_SECTION_LABELS, REPORT_WRITING_STYLE_LABELS, type ReportSectionId, type ReportTemplate } from "@/lib/report-template";
import { buildSourceUseWarnings } from "@/lib/source-use-warnings";
import type { WebPresence } from "@/lib/api/client";
import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BriefArtifact, BriefProvenanceItem, BriefSummaryItem } from "@/types/dossier";
import type { CddOrchestrationTrace } from "@/types/orchestration";

type ExportDossierPdfOptions = {
  analystMemo?: AnalystMemoReady;
  filename?: string;
  generatedAt?: Date;
  orchestration?: CddOrchestrationTrace;
  reportTemplate?: ReportTemplate;
  webPresence?: WebPresence;
};

type PdfDoc = InstanceType<typeof JsPdfInstance>;

const EVIDENCE_TYPE_LABELS: Record<NonNullable<BriefProvenanceItem["evidenceType"]>, string> = {
  official_registry: "Official registry evidence",
  operational_metadata: "Operational metadata",
  web_discovery: "Web discovery",
};

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function addWrappedText(doc: PdfDoc, text: string, x: number, y: number, maxWidth: number): number {
  const lines = doc.splitTextToSize(text, maxWidth) as string[];
  doc.text(lines, x, y);
  return y + lines.length * 5;
}

function addSectionTitle(doc: PdfDoc, title: string, y: number): number {
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.setTextColor(15, 23, 42);
  doc.text(title, 20, y);
  return y + 7;
}

function ensurePage(doc: PdfDoc, y: number): number {
  if (y <= 275) {
    return y;
  }
  doc.addPage();
  return 20;
}

function addSummaryRows(doc: PdfDoc, rows: BriefSummaryItem[], y: number, maxWidth: number): number {
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(51, 65, 85);

  for (const row of rows) {
    y = ensurePage(doc, y);
    const source = row.source === undefined || row.source === null ? "" : ` (${row.source})`;
    const text = `${row.label}: ${stringifyValue(row.value)}${source}`;
    y = addWrappedText(doc, text, 22, y, maxWidth - 4) + 2;
  }

  return y;
}

function getEvidenceTypeLabel(item: BriefProvenanceItem): string {
  return EVIDENCE_TYPE_LABELS[item.evidenceType ?? "official_registry"];
}

function addRecordRows(
  doc: PdfDoc,
  records: Record<string, unknown>[],
  y: number,
  maxWidth: number,
): number {
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(51, 65, 85);

  if (records.length === 0) {
    return addWrappedText(doc, "No matching records returned.", 22, y, maxWidth - 4) + 2;
  }

  for (const record of records) {
    y = ensurePage(doc, y);
    const fields = Object.entries(record)
      .map(([key, value]) => `${key}: ${formatRecordValue(key, value)}`)
      .join("; ");
    y = addWrappedText(doc, fields, 22, y, maxWidth - 4) + 3;
  }

  return y;
}

export async function exportDossierPdf(
  brief: BriefArtifact,
  options: ExportDossierPdfOptions = {},
): Promise<void> {
  const { default: jsPDF } = await import("jspdf");
  const doc = new jsPDF();
  const generatedAt = options.generatedAt ?? new Date();
  const template = options.reportTemplate ?? DEFAULT_REPORT_TEMPLATE;
  const includes = (section: ReportSectionId): boolean => template.sections.includes(section);
  const manifest = await buildDossierExportManifest({
    dossier: brief,
    generatedAt: generatedAt.toISOString(),
    ...(options.analystMemo === undefined ? {} : { analystMemo: options.analystMemo }),
    ...(options.orchestration === undefined ? {} : { orchestration: options.orchestration }),
    ...(options.webPresence === undefined ? {} : { webPresence: options.webPresence }),
  });
  const sourceUseWarnings = buildSourceUseWarnings({
    dossier: brief,
    ...(options.webPresence === undefined ? {} : { webPresence: options.webPresence }),
  });
  const pageWidth = doc.internal.pageSize.getWidth();
  const maxWidth = pageWidth - 40;
  let y = 20;

  doc.setProperties({
    title: `${brief.title} - Dude diligence brief`,
    subject: "Singapore counterparty due diligence brief",
    author: "Dude",
    creator: "Dude",
  });

  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.setTextColor(15, 23, 42);
  doc.text(brief.title, 20, y);
  y += 8;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(100, 116, 139);
  doc.text(`Generated: ${generatedAt.toLocaleString("en-SG")}`, 20, y);
  y += 5;
  doc.text(`Report style: ${REPORT_WRITING_STYLE_LABELS[template.writingStyle]}`, 20, y);
  y += 12;

  if (sourceUseWarnings.length > 0) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, "Source-use warnings", y);
    y = addSummaryRows(
      doc,
      sourceUseWarnings.map((warning) => ({
        label: warning.title,
        value: `${warning.message} Triggered by: ${warning.triggeredBy.join(", ")}`,
      })),
      y,
      maxWidth,
    ) + 4;
  }

  if (includes("executive_summary")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.executive_summary, y);
    y = addSummaryRows(doc, brief.summary, y, maxWidth) + 4;
  }

  if (includes("coverage_matrix")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.coverage_matrix, y);
    y = addSummaryRows(
      doc,
      getSourceCoverage(brief).map((item) => ({
        label: item.label,
        value: [
          `status: ${sourceCoverageStatusLabel(item.status)}`,
          `coverage: ${sourceCoverageLevelLabel(item.coverageLevel)}`,
          `records: ${item.recordCount}`,
          `reason: ${item.reason}`,
          `tools: ${item.tools.join(", ")}`,
          item.gapCodes === undefined || item.gapCodes.length === 0 ? null : `gaps: ${item.gapCodes.join(", ")}`,
        ].filter(Boolean).join("; "),
      })),
      y,
      maxWidth,
    ) + 4;
  }

  const snapshot = buildDiligenceSnapshot(brief);
  if (includes("identity_snapshot")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.identity_snapshot, y);
    y = addSummaryRows(
      doc,
      [
        { label: "Status", value: snapshot.status },
        { label: "UEN", value: snapshot.uen },
        { label: "Entity type", value: snapshot.entityType },
        { label: "Entity age", value: snapshot.age },
        { label: "Address", value: snapshot.address },
        { label: "Primary SSIC", value: snapshot.primarySsic },
        { label: "Matched modules", value: snapshot.matchedModules },
        { label: "Confidence", value: snapshot.confidence },
      ],
      y,
      maxWidth,
    ) + 4;
  }

  if (includes("risk_assessment")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.risk_assessment, y);
    y = addSummaryRows(
      doc,
      (brief.riskFlags ?? []).length === 0
        ? [{ label: "Risk flags", value: "No risk flags returned." }]
        : (brief.riskFlags ?? []).map((flag) => ({
            label: `${riskSeverityLabel(flag)} - ${riskCodeLabel(flag.code)}`,
            value: `${flag.message} (${flag.source})`,
          })),
      y,
      maxWidth,
    ) + 2;

    y = addSummaryRows(
      doc,
      (brief.matchConfidence ?? []).length === 0
        ? [{ label: "Confidence", value: "No confidence details returned." }]
        : (brief.matchConfidence ?? []).map((match) => ({
            label: match.source,
            value: `${confidenceLabel(match.confidence)}${match.matchedOn === null ? "" : ` on ${match.matchedOn}`}`,
          })),
      y,
      maxWidth,
    ) + 4;
  }

  if (includes("executive_summary") || includes("action_plan")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, "Cited Analyst Summary", y);
    if (options.analystMemo === undefined) {
      y = addSummaryRows(
        doc,
        [{ label: "Memo", value: "Not included in this export." }],
        y,
        maxWidth,
      ) + 4;
    } else {
      const memo = options.analystMemo;
      y = addSummaryRows(
        doc,
        [
          { label: "Provider", value: `${memo.provider} / ${memo.model}` },
          { label: "Generated", value: formatTimestamp(memo.generatedAt) ?? memo.generatedAt },
          { label: "Risk rating", value: `${memo.riskRating.level}: ${memo.riskRating.rationale}` },
        ],
        y,
        maxWidth,
      ) + 2;
      if (includes("executive_summary")) {
        y = addSummaryRows(
          doc,
          memo.evidenceMemo.map((item, index) => ({
            label: `Finding ${index + 1}`,
            value: `${item.text} [${item.citationIds.join(", ")}]`,
          })),
          y,
          maxWidth,
        ) + 2;
      }
      if (includes("action_plan")) {
        y = addSummaryRows(
          doc,
          [
            ...memo.decisionAid.nextSteps.map((step, index) => ({
              label: `Next action ${index + 1}`,
              value: step,
            })),
            ...memo.decisionAid.confidenceBlockers.map((blocker, index) => ({
              label: `Confidence blocker ${index + 1}`,
              value: blocker,
            })),
            { label: "Non-advisory limit", value: memo.decisionAid.nonAdvisoryReminder },
          ],
          y,
          maxWidth,
        ) + 2;
      }
      y = addSummaryRows(
        doc,
        memo.citations.map((citation) => ({
          label: citation.id,
          value: `${citation.label}; ${citation.source}; ${citation.text}`,
        })),
        y,
        maxWidth,
      ) + 4;
    }
  }

  if (includes("evidence_records")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.evidence_records, y);
    y = addSummaryRows(doc, brief.evidence, y, maxWidth) + 4;
    for (const group of getDossierRecordGroups(brief)) {
      y = ensurePage(doc, y);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(10);
      doc.setTextColor(15, 23, 42);
      doc.text(group.label, 22, y);
      y += 6;

      for (const table of group.tables) {
        y = ensurePage(doc, y);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(9);
        doc.setTextColor(71, 85, 105);
        doc.text(table.label, 22, y);
        y += 5;
        y = addRecordRows(doc, table.records, y, maxWidth) + 2;
      }
    }
  }

  if (includes("supplemental_discovery")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.supplemental_discovery, y);
    y = addSummaryRows(
      doc,
      options.webPresence === undefined
        ? [{ label: "Web discovery", value: "Not included in this export." }]
        : [
            { label: "Evidence type", value: "Web discovery, not registry evidence." },
            { label: "TinyFish configured", value: options.webPresence.configured ? "yes" : "no" },
            { label: "Possible official website", value: options.webPresence.possibleOfficialWebsite },
            ...options.webPresence.results.map((result) => ({
              label: result.siteName ?? result.url,
              value: `${result.title} - ${result.url}`,
            })),
          ],
      y,
      maxWidth,
    ) + 4;
  }

  if (includes("gaps")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.gaps, y);
    const coverageGaps = getActionableSourceCoverageGaps(brief);
    y = addSummaryRows(
      doc,
      brief.gaps.length > 0
        ? brief.gaps.map((gap) => ({ label: gap.code, value: gap.message, source: "Gap" }))
        : coverageGaps.length > 0
          ? coverageGaps.map((item) => ({ label: item.label, value: item.reason, source: "Source coverage" }))
          : [{ label: "Gaps", value: "No gaps returned.", source: "Gap" }],
      y,
      maxWidth,
    ) + 4;
  }

  if (includes("action_plan")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.action_plan, y);
    y = addSummaryRows(
      doc,
      (brief.nextChecks ?? []).length === 0
        ? [{ label: "Next checks", value: "No follow-up checks returned." }]
        : (brief.nextChecks ?? []).map((check) => ({
            label: check.tool,
            value: `${check.reason}; suggested input: ${formatNextCheckInputSummary(check.input)}`,
          })),
      y,
      maxWidth,
    ) + 4;
  }

  if (includes("provenance")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.provenance, y);
    y = addSummaryRows(
      doc,
      brief.provenance.map((item) => ({
        label: item.source,
        value: [
          getEvidenceTypeLabel(item),
          item.tool,
          item.coverage,
          `records: ${item.recordCount}`,
          item.sourceUrl === undefined ? null : `source: ${item.sourceUrl}`,
        ].filter(Boolean).join("; "),
        source: item.authRequired ? "Auth required" : "No auth",
      })),
      y,
      maxWidth,
    ) + 4;
  }

  if (includes("freshness")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.freshness, y);
    y = addSummaryRows(
      doc,
      brief.freshness.map((item) => ({
        label: item.source,
        value: [
          `Checked by Dude: ${formatTimestamp(item.observedAt) ?? item.observedAt}`,
          `Source record date: ${formatTimestamp(item.upstreamTimestamp ?? null) ?? "Not provided"}`,
        ].join("; "),
      })),
      y,
      maxWidth,
    ) + 4;
  }

  if (includes("limits")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.limits, y);
    y = addSummaryRows(
      doc,
      brief.limits.map((limit) => ({ label: limit.code, value: limit.message })),
      y,
      maxWidth,
    ) + 4;

    y = ensurePage(doc, y);
    y = addSectionTitle(doc, "Compliance Use Notice", y);
    y = addSummaryRows(doc, [...complianceUseLimitations], y, maxWidth) + 4;
  }

  if (includes("manifest")) {
    y = ensurePage(doc, y);
    y = addSectionTitle(doc, REPORT_SECTION_LABELS.manifest, y);
    addSummaryRows(
      doc,
      [
        { label: "Manifest schema", value: manifest.schemaVersion },
        { label: "Dossier hash", value: manifest.dossierHash },
        { label: "Signature", value: `${manifest.signature.algorithm}: ${manifest.signature.value}` },
        { label: "Generated", value: manifest.generatedAt },
        { label: "Tool version", value: manifest.toolVersion },
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
        { label: "Signature note", value: manifest.signature.note },
      ],
      y,
      maxWidth,
    );
  }

  doc.save(options.filename ?? "dude-diligence-brief.pdf");
}
