import type { jsPDF as JsPdfInstance } from "jspdf";
import {
  buildDiligenceSnapshot,
  confidenceLabel,
  formatTimestamp,
  formatRecordValue,
  getDossierRecordGroups,
  riskSeverityLabel,
} from "@/lib/dossier";
import { complianceUseLimitations } from "@/lib/compliance";
import { buildDossierExportManifest } from "@/lib/export/manifest";
import type { WebPresence } from "@/lib/api/client";
import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BriefArtifact, BriefProvenanceItem, BriefSummaryItem } from "@/types/dossier";

type ExportDossierPdfOptions = {
  analystMemo?: AnalystMemoReady;
  filename?: string;
  generatedAt?: Date;
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
  const manifest = await buildDossierExportManifest({
    dossier: brief,
    generatedAt: generatedAt.toISOString(),
    ...(options.analystMemo === undefined ? {} : { analystMemo: options.analystMemo }),
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
  y += 12;

  y = addSectionTitle(doc, "Summary", y);
  y = addSummaryRows(doc, brief.summary, y, maxWidth) + 4;

  const snapshot = buildDiligenceSnapshot(brief);
  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Diligence Snapshot", y);
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

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Risk Signals", y);
  y = addSummaryRows(
    doc,
    (brief.riskFlags ?? []).length === 0
      ? [{ label: "Risk flags", value: "No risk flags returned." }]
      : (brief.riskFlags ?? []).map((flag) => ({
          label: `${riskSeverityLabel(flag)} - ${flag.code}`,
          value: `${flag.message} (${flag.source})`,
        })),
    y,
    maxWidth,
  ) + 4;

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Match Confidence", y);
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

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Analyst Memo", y);
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
    y = addSummaryRows(
      doc,
      memo.evidenceMemo.map((item, index) => ({
        label: `Memo point ${index + 1}`,
        value: `${item.text} [${item.citationIds.join(", ")}]`,
      })),
      y,
      maxWidth,
    ) + 2;
    y = addSummaryRows(
      doc,
      [
        ...memo.decisionAid.nextSteps.map((step, index) => ({
          label: `Decision aid ${index + 1}`,
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

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Evidence", y);
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

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Web Presence", y);
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

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Gaps", y);
  y = addSummaryRows(
    doc,
    brief.gaps.map((gap) => ({ label: gap.code, value: gap.message, source: "Gap" })),
    y,
    maxWidth,
  ) + 4;

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "What To Check Next", y);
  y = addSummaryRows(
    doc,
    (brief.nextChecks ?? []).length === 0
      ? [{ label: "Next checks", value: "No follow-up checks returned." }]
      : (brief.nextChecks ?? []).map((check) => ({
          label: check.tool,
          value: `${check.reason}; input: ${JSON.stringify(check.input)}`,
        })),
    y,
    maxWidth,
  ) + 4;

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Provenance", y);
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

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Freshness", y);
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

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Limits", y);
  y = addSummaryRows(
    doc,
    brief.limits.map((limit) => ({ label: limit.code, value: limit.message })),
    y,
    maxWidth,
  ) + 4;

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Compliance Use Notice", y);
  y = addSummaryRows(doc, [...complianceUseLimitations], y, maxWidth) + 4;

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Export Manifest", y);
  addSummaryRows(
    doc,
    [
      { label: "Manifest schema", value: manifest.schemaVersion },
      { label: "Dossier hash", value: manifest.dossierHash },
      { label: "Signature", value: `${manifest.signature.algorithm}: ${manifest.signature.value}` },
      { label: "Generated", value: manifest.generatedAt },
      { label: "Tool version", value: manifest.toolVersion },
      { label: "Signature note", value: manifest.signature.note },
    ],
    y,
    maxWidth,
  );

  doc.save(options.filename ?? "dude-diligence-brief.pdf");
}
