import {
  getDossierConfidence,
  getSummaryString,
  sanitizeFilenamePart,
} from "@/lib/dossier";
import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BulkDossierRow, ShortlistEntry } from "@/types/bulk";
import type { BusinessDossier } from "@/types/dossier";
import type { WebPresence } from "@/lib/api/client";

const downloadText = (filename: string, mimeType: string, text: string): void => {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
};

const csvEscape = (value: unknown): string => {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, "\"\"")}"` : text;
};

const toCsv = (rows: Record<string, unknown>[]): string => {
  if (rows.length === 0) return "";
  const columns = Object.keys(rows[0] ?? {});
  return [
    columns.map(csvEscape).join(","),
    ...rows.map((row) => columns.map((column) => csvEscape(row[column])).join(",")),
  ].join("\n");
};

export function buildDossierExportSummary(dossier: BusinessDossier): ShortlistEntry {
  const confidence = getDossierConfidence(dossier);
  const riskFlags = dossier.riskFlags ?? [];
  const gapCodes = dossier.gaps.map((gap) => gap.code);
  const uen = getSummaryString(dossier, "UEN");
  const entity = getSummaryString(dossier, "Entity");
  return {
    canonicalIdentifier: uen ?? entity ?? dossier.title,
    confidence: confidence?.level ?? null,
    entity,
    entityStatus: getSummaryString(dossier, "Entity status"),
    gapCodes,
    provenanceSources: dossier.provenance.map((item) => item.source),
    risk: riskFlags.some((flag) => flag.severity === "high")
      ? "high"
      : riskFlags.some((flag) => flag.severity === "medium")
        ? "medium"
        : riskFlags.some((flag) => flag.severity === "low")
          ? "low"
          : "none",
    riskFlags: riskFlags.map((flag) => flag.code),
    savedAt: new Date().toISOString(),
    uen,
  };
}

const singleDossierRow = (dossier: BusinessDossier): Record<string, unknown> => {
  const summary = buildDossierExportSummary(dossier);
  return {
    confidence: summary.confidence,
    entity: summary.entity,
    entityStatus: summary.entityStatus,
    gapCodes: summary.gapCodes.join(";"),
    generatedAt: new Date().toISOString(),
    limits: dossier.limits.map((limit) => `${limit.code}: ${limit.message}`).join(";"),
    provenance: summary.provenanceSources.join(";"),
    risk: summary.risk,
    riskFlags: summary.riskFlags.join(";"),
    uen: summary.uen,
  };
};

export function exportSingleDossierJson(params: {
  dossier: BusinessDossier;
  analystMemo?: AnalystMemoReady;
  webPresence?: WebPresence;
}): void {
  const identifier = sanitizeFilenamePart(getSummaryString(params.dossier, "UEN") ?? params.dossier.title);
  downloadText(
    `dude-diligence-${identifier}.json`,
    "application/json",
    JSON.stringify({
      analystMemo: params.analystMemo ?? null,
      dossier: params.dossier,
      generatedAt: new Date().toISOString(),
      limits: params.dossier.limits,
      webPresence: params.webPresence ?? null,
    }, null, 2),
  );
}

export function exportSingleDossierCsv(dossier: BusinessDossier): void {
  const identifier = sanitizeFilenamePart(getSummaryString(dossier, "UEN") ?? dossier.title);
  downloadText(`dude-diligence-${identifier}.csv`, "text/csv", toCsv([singleDossierRow(dossier)]));
}

const bulkRowsForExport = (rows: readonly BulkDossierRow[]): Record<string, unknown>[] =>
  rows.map((row) => ({
    confidence: row.confidence,
    entity: row.entity,
    entityStatus: row.entityStatus,
    gapCodes: row.gapCodes.join(";"),
    input: row.input,
    matchedModules: row.matchedModules.join(";"),
    provenance: row.provenanceSources.join(";"),
    risk: row.risk,
    riskFlags: row.riskFlags.join(";"),
    status: row.status,
    uen: row.uen,
    upstreamFailure: row.upstreamFailure,
  }));

export function exportBulkJson(rows: readonly BulkDossierRow[], generatedAt = new Date().toISOString()): void {
  downloadText(
    `dude-bulk-diligence-${generatedAt.slice(0, 10)}.json`,
    "application/json",
    JSON.stringify({ generatedAt, rows }, null, 2),
  );
}

export function exportBulkCsv(rows: readonly BulkDossierRow[], generatedAt = new Date().toISOString()): void {
  downloadText(
    `dude-bulk-diligence-${generatedAt.slice(0, 10)}.csv`,
    "text/csv",
    toCsv(bulkRowsForExport(rows)),
  );
}

export function exportShortlistJson(entries: readonly ShortlistEntry[]): void {
  const generatedAt = new Date().toISOString();
  downloadText(
    `dude-shortlist-${generatedAt.slice(0, 10)}.json`,
    "application/json",
    JSON.stringify({ generatedAt, entries }, null, 2),
  );
}

export function exportShortlistCsv(entries: readonly ShortlistEntry[]): void {
  const rows = entries.map((entry) => ({
    confidence: entry.confidence,
    entity: entry.entity,
    entityStatus: entry.entityStatus,
    gapCodes: entry.gapCodes.join(";"),
    provenance: entry.provenanceSources.join(";"),
    risk: entry.risk,
    riskFlags: entry.riskFlags.join(";"),
    savedAt: entry.savedAt,
    uen: entry.uen,
  }));
  downloadText(`dude-shortlist-${new Date().toISOString().slice(0, 10)}.csv`, "text/csv", toCsv(rows));
}
