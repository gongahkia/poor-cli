import {
  getDossierConfidence,
  getSourceCoverage,
  getSummaryString,
  sanitizeFilenamePart,
  sourceCoverageLevelLabel,
  sourceCoverageStatusLabel,
} from "@/lib/dossier";
import {
  buildComplianceUseLimitations,
  buildComplianceUseSummary,
} from "@/lib/compliance";
import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BulkDossierRow } from "@/types/bulk";
import type { BusinessDossier } from "@/types/dossier";
import type { CddOrchestrationTrace } from "@/types/orchestration";
import type { PeopleDiscovery, WebPresence } from "@/lib/api/client";
import type { ReportTemplate } from "@/lib/report-template";
import {
  buildDossierExportManifest,
  type DossierExportManifest,
} from "@/lib/export/manifest";
import {
  buildSourceUseWarnings,
  buildSourceUseWarningsFromSources,
  formatSourceUseWarnings,
} from "@/lib/source-use-warnings";
import { followUpPriorityLabel, getAnalystFollowUps } from "@/lib/next-checks";

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

type DossierExportSummary = {
  canonicalIdentifier: string;
  confidence: string | null;
  entity: string | null;
  entityStatus: string | null;
  gapCodes: string[];
  provenanceSources: string[];
  risk: BulkDossierRow["risk"];
  riskFlags: string[];
  uen: string | null;
};

function buildDossierExportSummary(dossier: BusinessDossier): DossierExportSummary {
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
    uen,
  };
}

export const buildSingleDossierCsvRow = (
  dossier: BusinessDossier,
  generatedAt = new Date().toISOString(),
  orchestration?: CddOrchestrationTrace,
): Record<string, unknown> => {
  const summary = buildDossierExportSummary(dossier);
  const sourceUseWarnings = buildSourceUseWarnings({ dossier });
  const analystFollowUps = getAnalystFollowUps(dossier);
  return {
    analystFollowUps: analystFollowUps
      .map((followUp) => `${followUpPriorityLabel(followUp.priority)}:${followUp.category}:${followUp.action}:${followUp.reason}`)
      .join(";"),
    complianceUseNotice: buildComplianceUseSummary(),
    confidence: summary.confidence,
    entity: summary.entity,
    entityStatus: summary.entityStatus,
    gapCodes: summary.gapCodes.join(";"),
    generatedAt,
    limits: dossier.limits.map((limit) => `${limit.code}: ${limit.message}`).join(";"),
    orchestrationStatus: orchestration?.status ?? "",
    orchestrationStages: orchestration?.stages?.map((stage) => `${stage.label}:${stage.status}`).join(";") ?? "",
    provenance: summary.provenanceSources.join(";"),
    risk: summary.risk,
    riskFlags: summary.riskFlags.join(";"),
    sourceCoverage: getSourceCoverage(dossier)
      .map((item) => `${item.label}:${sourceCoverageStatusLabel(item.status)}/${sourceCoverageLevelLabel(item.coverageLevel)}:${item.reason}`)
      .join(";"),
    sourceUseWarnings: formatSourceUseWarnings(sourceUseWarnings),
    uen: summary.uen,
  };
};

export async function buildSingleDossierJsonPayload(params: {
  dossier: BusinessDossier;
  analystMemo?: AnalystMemoReady;
  generatedAt?: string;
  orchestration?: CddOrchestrationTrace;
  peopleDiscovery?: PeopleDiscovery;
  reportTemplate?: ReportTemplate;
  webPresence?: WebPresence;
}): Promise<Record<string, unknown>> {
  const generatedAt = params.generatedAt ?? new Date().toISOString();
  const manifest = await buildDossierExportManifest({
    dossier: params.dossier,
    generatedAt,
    ...(params.analystMemo === undefined ? {} : { analystMemo: params.analystMemo }),
    ...(params.orchestration === undefined ? {} : { orchestration: params.orchestration }),
    ...(params.peopleDiscovery === undefined ? {} : { peopleDiscovery: params.peopleDiscovery }),
    ...(params.reportTemplate === undefined ? {} : { reportTemplate: params.reportTemplate }),
    ...(params.webPresence === undefined ? {} : { webPresence: params.webPresence }),
  });
  return {
    analystMemo: params.analystMemo ?? null,
    complianceUse: buildComplianceUseLimitations(),
    dossier: params.dossier,
    generatedAt,
    analystFollowUps: getAnalystFollowUps(params.dossier),
    limits: params.dossier.limits,
    manifest,
    orchestration: params.orchestration ?? null,
    peopleDiscovery: params.peopleDiscovery ?? null,
    reportReadiness: manifest.reportReadiness,
    reportTemplate: manifest.reportTemplate,
    reviewerMetadata: manifest.reviewerMetadata,
    sourceCoverage: params.dossier.sourceCoverage ?? [],
    sourceUseWarnings: manifest.sourceUseWarnings,
    webPresence: params.webPresence ?? null,
  };
}

export async function exportSingleDossierJson(params: {
  dossier: BusinessDossier;
  analystMemo?: AnalystMemoReady;
  orchestration?: CddOrchestrationTrace;
  peopleDiscovery?: PeopleDiscovery;
  reportTemplate?: ReportTemplate;
  webPresence?: WebPresence;
}): Promise<void> {
  const identifier = sanitizeFilenamePart(getSummaryString(params.dossier, "UEN") ?? params.dossier.title);
  const payload = await buildSingleDossierJsonPayload(params);
  downloadText(
    `dude-diligence-${identifier}.json`,
    "application/json",
    JSON.stringify(payload, null, 2),
  );
}

export async function exportSingleDossierCsv(
  dossier: BusinessDossier,
  options: { orchestration?: CddOrchestrationTrace } = {},
): Promise<void> {
  const identifier = sanitizeFilenamePart(getSummaryString(dossier, "UEN") ?? dossier.title);
  const generatedAt = new Date().toISOString();
  const manifest = await buildDossierExportManifest({
    dossier,
    generatedAt,
    ...(options.orchestration === undefined ? {} : { orchestration: options.orchestration }),
  });
  downloadText(
    `dude-diligence-${identifier}.csv`,
    "text/csv",
    toCsv([{
      ...buildSingleDossierCsvRow(dossier, generatedAt, options.orchestration),
      manifestSchemaVersion: manifest.schemaVersion,
      manifestSignature: manifest.signature.value,
      dossierHash: manifest.dossierHash,
    }]),
  );
}

const bulkRowsForExport = (rows: readonly BulkDossierRow[]): Record<string, unknown>[] =>
  rows.map((row) => {
    const warnings = row.dossier === undefined
      ? buildSourceUseWarningsFromSources(row.provenanceSources)
      : buildSourceUseWarnings({
          dossier: row.dossier,
          ...(row.peopleDiscovery === undefined ? {} : { peopleDiscovery: row.peopleDiscovery }),
          ...(row.webPresence === undefined ? {} : { webPresence: row.webPresence }),
        });
    return {
      complianceUseNotice: buildComplianceUseSummary(),
      confidence: row.confidence,
      entity: row.entity,
      entityStatus: row.entityStatus,
      gapCodes: row.gapCodes.join(";"),
      input: row.input,
      matchedModules: row.matchedModules.join(";"),
      orchestrationStatus: row.orchestration?.status ?? "",
      orchestrationStages: row.orchestration?.stages?.map((stage) => `${stage.label}:${stage.status}`).join(";") ?? "",
      provenance: row.provenanceSources.join(";"),
      risk: row.risk,
      riskFlags: row.riskFlags.join(";"),
      sourceCoverage: row.dossier === undefined
        ? ""
        : getSourceCoverage(row.dossier)
            .map((item) => `${item.label}:${sourceCoverageStatusLabel(item.status)}/${sourceCoverageLevelLabel(item.coverageLevel)}:${item.reason}`)
            .join(";"),
      sourceUseWarnings: formatSourceUseWarnings(warnings),
      status: row.status,
      uen: row.uen,
      upstreamFailure: row.upstreamFailure,
    };
  });

const buildBulkManifest = async (
  rows: readonly BulkDossierRow[],
  generatedAt: string,
): Promise<Map<number, DossierExportManifest>> => {
  const manifestEntries = await Promise.all(rows
    .filter((row): row is BulkDossierRow & { dossier: BusinessDossier } => row.dossier !== undefined)
    .map(async (row) => [
      row.index,
      await buildDossierExportManifest({
        dossier: row.dossier,
        generatedAt,
        ...(row.peopleDiscovery === undefined ? {} : { peopleDiscovery: row.peopleDiscovery }),
        ...(row.webPresence === undefined ? {} : { webPresence: row.webPresence }),
      }),
    ] as const));
  return new Map(manifestEntries);
};

export async function exportBulkJson(rows: readonly BulkDossierRow[], generatedAt = new Date().toISOString()): Promise<void> {
  const manifestByIndex = await buildBulkManifest(rows, generatedAt);
  downloadText(
    `dude-bulk-diligence-${generatedAt.slice(0, 10)}.json`,
    "application/json",
    JSON.stringify({
      complianceUse: buildComplianceUseLimitations(),
      generatedAt,
      manifests: Array.from(manifestByIndex, ([rowIndex, manifest]) => ({ rowIndex, manifest })),
      rows,
      sourceUseWarnings: rows.flatMap((row) => row.dossier === undefined
        ? buildSourceUseWarningsFromSources(row.provenanceSources)
        : buildSourceUseWarnings({
            dossier: row.dossier,
            ...(row.peopleDiscovery === undefined ? {} : { peopleDiscovery: row.peopleDiscovery }),
            ...(row.webPresence === undefined ? {} : { webPresence: row.webPresence }),
          })),
    }, null, 2),
  );
}

export async function exportBulkCsv(rows: readonly BulkDossierRow[], generatedAt = new Date().toISOString()): Promise<void> {
  const manifestByIndex = await buildBulkManifest(rows, generatedAt);
  downloadText(
    `dude-bulk-diligence-${generatedAt.slice(0, 10)}.csv`,
    "text/csv",
    toCsv(bulkRowsForExport(rows).map((row, index) => {
      const source = rows[index];
      const manifest = source === undefined ? undefined : manifestByIndex.get(source.index);
      return {
        ...row,
        dossierHash: manifest?.dossierHash ?? "",
        manifestSignature: manifest?.signature.value ?? "",
      };
    })),
  );
}
