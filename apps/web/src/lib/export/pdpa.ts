import type { jsPDF as JsPdfInstance } from "jspdf";
import {
  buildPdpaChecklistReport,
  pdpaStatusLabel,
} from "@/lib/pdpa";
import type { BusinessDossier } from "@/types/dossier";

type PdfDoc = InstanceType<typeof JsPdfInstance>;

export type ExportPdpaReportOptions = {
  filename?: string;
  generatedAt?: Date;
  reviewedItemIds?: readonly string[];
};

const stringify = (value: string | null): string =>
  value === null || value.trim() === "" ? "Not available" : value;

function ensurePage(doc: PdfDoc, y: number): number {
  if (y <= 275) {
    return y;
  }
  doc.addPage();
  return 20;
}

function addWrappedText(doc: PdfDoc, text: string, x: number, y: number, maxWidth: number): number {
  const lines = doc.splitTextToSize(text, maxWidth) as string[];
  doc.text(lines, x, y);
  return y + lines.length * 5;
}

function addSectionTitle(doc: PdfDoc, title: string, y: number): number {
  y = ensurePage(doc, y);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.setTextColor(15, 23, 42);
  doc.text(title, 20, y);
  return y + 7;
}

function addBullets(doc: PdfDoc, values: readonly string[], y: number, maxWidth: number): number {
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(51, 65, 85);
  if (values.length === 0) {
    return addWrappedText(doc, "- None returned.", 22, y, maxWidth - 4) + 2;
  }
  for (const value of values) {
    y = ensurePage(doc, y);
    y = addWrappedText(doc, `- ${value}`, 22, y, maxWidth - 4) + 1;
  }
  return y;
}

export async function exportPdpaReportPdf(
  dossier: BusinessDossier,
  options: ExportPdpaReportOptions = {},
): Promise<void> {
  const { default: jsPDF } = await import("jspdf");
  const doc = new jsPDF();
  const generatedAt = options.generatedAt ?? new Date();
  const reviewed = new Set(options.reviewedItemIds ?? []);
  const report = buildPdpaChecklistReport(dossier, generatedAt);
  const pageWidth = doc.internal.pageSize.getWidth();
  const maxWidth = pageWidth - 40;
  let y = 20;

  doc.setProperties({
    title: report.title,
    subject: "PDPA vendor diligence checklist",
    author: "Dude",
    creator: "Dude",
  });

  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.setTextColor(15, 23, 42);
  y = addWrappedText(doc, report.title, 20, y, maxWidth) + 3;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(100, 116, 139);
  doc.text(`Generated: ${generatedAt.toLocaleString("en-SG")}`, 20, y);
  y += 6;
  doc.text(`Entity: ${stringify(report.entityName)}`, 20, y);
  y += 5;
  doc.text(`UEN: ${stringify(report.uen)}`, 20, y);
  y += 9;

  y = addSectionTitle(doc, "Notice", y);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(51, 65, 85);
  y = addWrappedText(doc, report.nonAdviceNotice, 22, y, maxWidth - 4) + 4;

  for (const item of report.items) {
    y = addSectionTitle(doc, item.title, y);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(51, 65, 85);
    y = addWrappedText(
      doc,
      [
        `Obligation: ${item.obligation}`,
        `Status: ${pdpaStatusLabel(item.status)}`,
        `Reviewed: ${reviewed.has(item.id) ? "yes" : "no"}`,
        `Source: ${item.sourceSection}`,
      ].join("; "),
      22,
      y,
      maxWidth - 4,
    ) + 2;

    doc.setFont("helvetica", "bold");
    doc.text("Evidence", 22, y);
    y += 5;
    y = addBullets(doc, item.evidence, y, maxWidth) + 2;

    doc.setFont("helvetica", "bold");
    doc.text("Gaps", 22, y);
    y += 5;
    y = addBullets(doc, item.gaps, y, maxWidth) + 2;

    doc.setFont("helvetica", "bold");
    doc.text("Action", 22, y);
    y += 5;
    doc.setFont("helvetica", "normal");
    y = addWrappedText(doc, item.action, 22, y, maxWidth - 4) + 4;
  }

  y = addSectionTitle(doc, "PDPC Sources", y);
  y = addBullets(
    doc,
    report.citations.map((citation) => `${citation.id}: ${citation.label} - ${citation.url}`),
    y,
    maxWidth,
  );

  doc.save(options.filename ?? "dude-pdpa-vendor-diligence-checklist.pdf");
}
