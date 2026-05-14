import type { jsPDF as JsPdfInstance } from "jspdf";
import type { BriefArtifact, BriefSummaryItem } from "@/types/dossier";

type ExportDossierPdfOptions = {
  filename?: string;
  generatedAt?: Date;
};

type PdfDoc = InstanceType<typeof JsPdfInstance>;

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

export async function exportDossierPdf(
  brief: BriefArtifact,
  options: ExportDossierPdfOptions = {},
): Promise<void> {
  const { default: jsPDF } = await import("jspdf");
  const doc = new jsPDF();
  const generatedAt = options.generatedAt ?? new Date();
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

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Evidence", y);
  y = addSummaryRows(doc, brief.evidence, y, maxWidth) + 4;

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Gaps", y);
  y = addSummaryRows(
    doc,
    brief.gaps.map((gap) => ({ label: gap.code, value: gap.message, source: "Gap" })),
    y,
    maxWidth,
  ) + 4;

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Provenance", y);
  y = addSummaryRows(
    doc,
    brief.provenance.map((item) => ({
      label: item.source,
      value: `${item.tool}; ${item.coverage}; records: ${item.recordCount}`,
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
      value: `Observed ${item.observedAt}; upstream ${item.upstreamTimestamp ?? "not available"}`,
    })),
    y,
    maxWidth,
  ) + 4;

  y = ensurePage(doc, y);
  y = addSectionTitle(doc, "Limits", y);
  addSummaryRows(
    doc,
    brief.limits.map((limit) => ({ label: limit.code, value: limit.message })),
    y,
    maxWidth,
  );

  doc.save(options.filename ?? "dude-diligence-brief.pdf");
}
