import {
  AlignmentType,
  Document,
  HeadingLevel,
  Packer,
  Paragraph,
  TextRun,
} from "docx";

import {
  buildDiligenceSnapshot,
  confidenceLabel,
  formatRecordValue,
  formatTimestamp,
  getActionableSourceCoverageGaps,
  getDossierRecordGroups,
  getSourceCoverage,
  riskCodeLabel,
  riskSeverityLabel,
  sanitizeFilenamePart,
  sourceCoverageLevelLabel,
  sourceCoverageStatusLabel,
} from "@/lib/dossier";
import { buildDossierExportManifest } from "@/lib/export/manifest";
import { formatNextCheckInputSummary } from "@/lib/next-checks";
import { buildSourceUseWarnings } from "@/lib/source-use-warnings";
import {
  DEFAULT_REPORT_TEMPLATE,
  REPORT_SECTION_LABELS,
  REPORT_WRITING_STYLE_LABELS,
  type ReportSectionId,
  type ReportTemplate,
} from "@/lib/report-template";
import type { WebPresence } from "@/lib/api/client";
import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BriefArtifact, BriefSummaryItem } from "@/types/dossier";
import type { CddOrchestrationTrace } from "@/types/orchestration";

type ExportDossierDocxOptions = {
  analystMemo?: AnalystMemoReady;
  filename?: string;
  generatedAt?: Date;
  orchestration?: CddOrchestrationTrace;
  reportTemplate?: ReportTemplate;
  webPresence?: WebPresence;
};

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function paragraph(text: string, options: { bold?: boolean; bullet?: boolean } = {}): Paragraph {
  return new Paragraph({
    bullet: options.bullet ? { level: 0 } : undefined,
    children: [new TextRun({ bold: options.bold, text })],
    spacing: { after: 120 },
  });
}

function heading(text: string): Paragraph {
  return new Paragraph({
    children: [new TextRun(text)],
    heading: HeadingLevel.HEADING_2,
    spacing: { after: 180, before: 240 },
  });
}

function rowsToParagraphs(rows: readonly BriefSummaryItem[]): Paragraph[] {
  return rows.map((row) =>
    paragraph(`${row.label}: ${stringifyValue(row.value)}${row.source === undefined ? "" : ` (${row.source})`}`),
  );
}

function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function exportDossierDocx(
  dossier: BriefArtifact,
  options: ExportDossierDocxOptions = {},
): Promise<void> {
  const generatedAt = options.generatedAt ?? new Date();
  const template = options.reportTemplate ?? DEFAULT_REPORT_TEMPLATE;
  const includes = (section: ReportSectionId): boolean => template.sections.includes(section);
  const manifest = await buildDossierExportManifest({
    dossier,
    generatedAt: generatedAt.toISOString(),
    ...(options.analystMemo === undefined ? {} : { analystMemo: options.analystMemo }),
    ...(options.orchestration === undefined ? {} : { orchestration: options.orchestration }),
    ...(options.webPresence === undefined ? {} : { webPresence: options.webPresence }),
  });
  const sourceUseWarnings = buildSourceUseWarnings({
    dossier,
    ...(options.webPresence === undefined ? {} : { webPresence: options.webPresence }),
  });
  const children: Paragraph[] = [
    new Paragraph({
      alignment: AlignmentType.LEFT,
      children: [new TextRun({ bold: true, size: 34, text: dossier.title })],
      heading: HeadingLevel.TITLE,
      spacing: { after: 120 },
    }),
    paragraph(`Generated: ${generatedAt.toLocaleString("en-SG")}`),
    paragraph(`Report style: ${REPORT_WRITING_STYLE_LABELS[template.writingStyle]}`),
  ];

  if (sourceUseWarnings.length > 0) {
    children.push(heading("Source-use warnings"));
    sourceUseWarnings.forEach((warning) => {
      children.push(paragraph(`${warning.title}: ${warning.message} Triggered by: ${warning.triggeredBy.join(", ")}`, { bullet: true }));
    });
  }

  if (includes("executive_summary")) {
    children.push(heading(REPORT_SECTION_LABELS.executive_summary), ...rowsToParagraphs(dossier.summary));
  }

  if (includes("coverage_matrix")) {
    children.push(heading(REPORT_SECTION_LABELS.coverage_matrix));
    const coverage = getSourceCoverage(dossier);
    if (coverage.length === 0) {
      children.push(paragraph("No source coverage matrix was included in this dossier."));
    } else {
      coverage.forEach((item) => {
        children.push(paragraph(`${item.label}: ${sourceCoverageStatusLabel(item.status)}; ${sourceCoverageLevelLabel(item.coverageLevel)}; records: ${item.recordCount}; ${item.reason}; tools: ${item.tools.join(", ")}${item.gapCodes === undefined || item.gapCodes.length === 0 ? "" : `; gaps: ${item.gapCodes.join(", ")}`}`));
      });
    }
  }

  if ((includes("executive_summary") || includes("action_plan")) && options.analystMemo !== undefined) {
    const memo = options.analystMemo;
    children.push(
      heading("Cited analyst summary"),
      paragraph(`Provider: ${memo.provider} / ${memo.model}`),
      paragraph(`Risk rating: ${memo.riskRating.level}: ${memo.riskRating.rationale}`),
    );
    if (includes("executive_summary")) {
      memo.evidenceMemo.forEach((item, index) => {
        children.push(paragraph(`Finding ${index + 1}: ${item.text} [${item.citationIds.join(", ")}]`, { bullet: true }));
      });
    }
    if (includes("action_plan")) {
      memo.decisionAid.nextSteps.forEach((step) => children.push(paragraph(`Next action: ${step}`, { bullet: true })));
      memo.decisionAid.confidenceBlockers.forEach((blocker) => children.push(paragraph(`Confidence blocker: ${blocker}`, { bullet: true })));
      children.push(paragraph(`Non-advisory limit: ${memo.decisionAid.nonAdvisoryReminder}`));
    }
    memo.citations.forEach((citation) => {
      children.push(paragraph(`${citation.id}: ${citation.label}; ${citation.source}; ${citation.text}`));
    });
  } else if (includes("executive_summary") || includes("action_plan")) {
    children.push(heading("Cited analyst summary"), paragraph("Memo was not included in this export."));
  }

  if (includes("risk_assessment")) {
    children.push(heading(REPORT_SECTION_LABELS.risk_assessment));
    const flags = dossier.riskFlags ?? [];
    if (flags.length === 0) {
      children.push(paragraph("No risk flags returned."));
    } else {
      flags.forEach((flag) => children.push(paragraph(`${riskSeverityLabel(flag)} - ${riskCodeLabel(flag.code)}: ${flag.message} (${flag.source})`)));
    }
    const matches = dossier.matchConfidence ?? [];
    if (matches.length === 0) {
      children.push(paragraph("No confidence details returned."));
    } else {
      matches.forEach((match) => {
        children.push(paragraph(`${match.source}: ${confidenceLabel(match.confidence)}${match.matchedOn === null ? "" : ` on ${match.matchedOn}`}`));
      });
    }
  }

  if (includes("identity_snapshot")) {
    const snapshot = buildDiligenceSnapshot(dossier);
    children.push(
      heading(REPORT_SECTION_LABELS.identity_snapshot),
      ...rowsToParagraphs([
        { label: "Status", value: snapshot.status },
        { label: "UEN", value: snapshot.uen },
        { label: "Entity type", value: snapshot.entityType },
        { label: "Entity age", value: snapshot.age },
        { label: "Address", value: snapshot.address },
        { label: "Primary SSIC", value: snapshot.primarySsic },
        { label: "Matched modules", value: snapshot.matchedModules },
        { label: "Confidence", value: snapshot.confidence },
      ]),
    );
  }

  if (includes("evidence_records")) {
    children.push(heading(REPORT_SECTION_LABELS.evidence_records), ...rowsToParagraphs(dossier.evidence));
    for (const group of getDossierRecordGroups(dossier)) {
      children.push(paragraph(group.label, { bold: true }));
      for (const table of group.tables) {
        children.push(paragraph(table.label, { bold: true }));
        if (table.records.length === 0) {
          children.push(paragraph("No matching records returned."));
        } else {
          table.records.forEach((record) => {
            children.push(paragraph(Object.entries(record).map(([key, value]) => `${key}: ${formatRecordValue(key, value)}`).join("; ")));
          });
        }
      }
    }
  }

  if (includes("supplemental_discovery")) {
    children.push(heading(REPORT_SECTION_LABELS.supplemental_discovery));
    if (options.webPresence === undefined) {
      children.push(paragraph("Web discovery was not included in this export."));
    } else {
      children.push(
        paragraph("Evidence type: Web discovery, not official registry evidence."),
        paragraph(`Possible official website: ${options.webPresence.possibleOfficialWebsite ?? "Not available"}`),
      );
      options.webPresence.results.forEach((result) => {
        children.push(paragraph(`${result.siteName ?? result.url}: ${result.title} - ${result.url}`));
      });
    }
  }

  if (includes("gaps")) {
    children.push(heading(REPORT_SECTION_LABELS.gaps));
    const coverageGaps = getActionableSourceCoverageGaps(dossier);
    if (dossier.gaps.length === 0 && coverageGaps.length === 0) {
      children.push(paragraph("No gaps returned."));
    } else if (dossier.gaps.length === 0) {
      coverageGaps.forEach((item) => children.push(paragraph(`${item.label}: ${item.reason}`)));
    } else {
      dossier.gaps.forEach((gap) => children.push(paragraph(`${gap.code}: ${gap.message}`)));
    }
  }

  if (includes("action_plan")) {
    children.push(heading(REPORT_SECTION_LABELS.action_plan));
    const nextChecks = dossier.nextChecks ?? [];
    if (nextChecks.length === 0) {
      children.push(paragraph("No follow-up checks returned."));
    } else {
      nextChecks.forEach((check) => {
        children.push(paragraph(`${check.tool}: ${check.reason}; suggested input: ${formatNextCheckInputSummary(check.input)}`));
      });
    }
  }

  if (includes("provenance")) {
    children.push(heading(REPORT_SECTION_LABELS.provenance));
    dossier.provenance.forEach((item) => {
      children.push(paragraph(`${item.source}: ${item.tool}; ${item.coverage}; records: ${item.recordCount}${item.sourceUrl === undefined ? "" : `; ${item.sourceUrl}`}`));
    });
  }

  if (includes("freshness")) {
    children.push(heading(REPORT_SECTION_LABELS.freshness));
    dossier.freshness.forEach((item) => {
      children.push(paragraph(`${item.source}: checked ${formatTimestamp(item.observedAt) ?? item.observedAt}; source record date ${formatTimestamp(item.upstreamTimestamp ?? null) ?? "Not provided"}`));
    });
  }

  if (includes("limits")) {
    children.push(heading(REPORT_SECTION_LABELS.limits));
    dossier.limits.forEach((limit) => children.push(paragraph(`${limit.code}: ${limit.message}`)));
  }

  if (includes("manifest")) {
    children.push(
      heading(REPORT_SECTION_LABELS.manifest),
      paragraph(`Manifest schema: ${manifest.schemaVersion}`),
      paragraph(`Dossier hash: ${manifest.dossierHash}`),
      paragraph(`Signature: ${manifest.signature.algorithm}: ${manifest.signature.value}`),
      paragraph(`Generated: ${manifest.generatedAt}`),
      paragraph(`Tool version: ${manifest.toolVersion}`),
      paragraph(`Orchestration status: ${manifest.orchestration?.status ?? "Not included"}`),
      paragraph(`Orchestration strategy: ${manifest.orchestration?.strategy ?? "Not included"}`),
      paragraph(`Orchestration stages: ${manifest.orchestration?.stages.map((stage) => `${stage.label}: ${stage.status}`).join("; ") ?? "Not included"}`),
      paragraph(`Source-use warnings: ${manifest.sourceUseWarnings.length === 0 ? "None triggered" : manifest.sourceUseWarnings.map((warning) => `${warning.title}: ${warning.triggeredBy.join(", ")}`).join("; ")}`),
      paragraph(`Source coverage: ${manifest.sourceCoverage.length === 0 ? "Not included" : manifest.sourceCoverage.map((item) => `${item.label}: ${item.status}/${item.coverageLevel}`).join("; ")}`),
      paragraph(`Signature note: ${manifest.signature.note}`),
    );
  }

  const doc = new Document({
    creator: "Dude",
    description: "Singapore counterparty due diligence report",
    sections: [{ children }],
    title: `${dossier.title} - Dude CDD report`,
  });

  const blob = await Packer.toBlob(doc);
  const identifier = sanitizeFilenamePart(dossier.summary.find((item) => item.label === "UEN")?.value as string | undefined ?? dossier.title);
  downloadBlob(options.filename ?? `dude-cdd-report-${identifier}.docx`, blob);
}
