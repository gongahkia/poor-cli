import {
  BriefArtifactSchema,
  BusinessDossierBaseSchema,
  BusinessDossierSchema,
  EnvironmentBriefSchema,
  MacroBriefSchema,
  PropertyBriefBaseSchema,
  PropertyBriefSchema,
  TransportBriefSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@sg-apis/shared";
import type {
  BriefArtifact,
  BriefFreshnessItem,
  BriefLimit,
  BriefProvenanceItem,
  EvidenceGap,
  MatchConfidence,
  NextCheck,
  RiskFlag,
  ToolResult,
} from "@sg-apis/shared";
import { MasDataset } from "@sg-apis/shared";
import { getAcraEntities } from "../apis/acra/client.js";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../apis/bca/client.js";
import { getCeaSalespersons } from "../apis/cea/client.js";
import { getHdbResalePrices } from "../apis/hdb/client.js";
import {
  getBusArrivals,
  getTrafficIncidents,
  getTrainAlerts,
} from "../apis/lta/client.js";
import {
  getAirQuality,
  getForecast2Hr,
  getRainfall,
} from "../apis/nea/client.js";
import { geocode } from "../apis/onemap/client.js";
import { searchDatasets as searchSingStatDatasets } from "../apis/singstat/client.js";
import { getPropertyTransactions } from "../apis/ura/client.js";
import { fetchNormalizedMasRecords } from "./mas-tools.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import { lookupPlanningArea } from "./ura-tools.js";
import { z } from "zod";

const TransportBriefInputSchema = {
  busStopCode: z.string().min(5).optional(),
  serviceNo: z.string().min(1).optional(),
  format: z.enum(["json", "markdown"]).optional(),
};

const EnvironmentBriefInputSchema = {
  area: z.string().min(1).optional(),
  region: z.string().min(1).optional(),
  stationId: z.string().min(1).optional(),
  date: z.string().min(1).optional(),
  format: z.enum(["json", "markdown"]).optional(),
};

const renderSectionRows = (rows: readonly Record<string, unknown>[]): string => {
  return rows.length === 0 ? "_No data_" : formatResponse(rows as Record<string, unknown>[], "markdown");
};

const renderRecordSection = (label: string, value: unknown): string => {
  const heading = `### ${label}`;
  if (Array.isArray(value)) {
    return `${heading}\n${renderSectionRows(value as readonly Record<string, unknown>[])}`;
  }
  if (value !== null && typeof value === "object") {
    return `${heading}\n${formatResponse([value as Record<string, unknown>], "markdown")}`;
  }
  return `${heading}\n_No data_`;
};

const renderBriefMarkdown = (payload: BriefArtifact): string => {
  const sections = [
    `## ${payload.title}`,
    "",
    "### Summary",
    renderSectionRows(payload.summary.map((item) => ({
      label: item.label,
      value: item.value,
      source: item.source,
    }))),
    "",
    "### Evidence",
    renderSectionRows(payload.evidence.map((item) => ({
      label: item.label,
      value: item.value,
      source: item.source,
    }))),
    "",
    "### Gaps",
    renderSectionRows(payload.gaps.map((gap) => ({
      code: gap.code,
      message: gap.message,
    }))),
    "",
    "### Sources",
    renderSectionRows(payload.provenance.map((item) => ({
      source: item.source,
      tool: item.tool,
      coverage: item.coverage,
      authRequired: item.authRequired,
      recordCount: item.recordCount,
    }))),
    "",
    "### Freshness",
    renderSectionRows(payload.freshness.map((item) => ({
      source: item.source,
      observedAt: item.observedAt,
      upstreamTimestamp: item.upstreamTimestamp,
    }))),
    "",
    "### What This Does Not Do",
    renderSectionRows(payload.limits.map((item) => ({
      code: item.code,
      message: item.message,
    }))),
  ];

  if (payload.riskFlags !== undefined && payload.riskFlags.length > 0) {
    sections.push("");
    sections.push("### Risk Flags");
    sections.push(renderSectionRows(payload.riskFlags.map((f) => ({
      severity: f.severity,
      code: f.code,
      message: f.message,
      source: f.source,
    }))));
  }

  if (payload.matchConfidence !== undefined && payload.matchConfidence.length > 0) {
    sections.push("");
    sections.push("### Match Confidence");
    sections.push(renderSectionRows(payload.matchConfidence.map((m) => ({
      source: m.source,
      confidence: m.confidence,
      matchedOn: m.matchedOn,
    }))));
  }

  if (payload.nextChecks !== undefined && payload.nextChecks.length > 0) {
    sections.push("");
    sections.push("### Next Checks");
    sections.push(renderSectionRows(payload.nextChecks.map((c) => ({
      tool: c.tool,
      reason: c.reason,
    }))));
  }

  for (const [label, value] of Object.entries(payload.records)) {
    sections.push("");
    sections.push(renderRecordSection(label, value));
  }

  return sections.join("\n");
};

const toToolResult = (
  payload: BriefArtifact,
  format: "json" | "markdown",
): ToolResult => {
  const validated = BriefArtifactSchema.parse(payload) as BriefArtifact;
  return {
    content: [{
      type: "text",
      text: format === "json"
        ? formatResponse(validated as unknown as Record<string, unknown>, "json")
        : renderBriefMarkdown(validated),
    }],
    structuredContent: {
      record: validated,
    },
  };
};

const toGap = (code: string, message: string): EvidenceGap => ({ code, message });
const toLimit = (code: string, message: string): BriefLimit => ({ code, message });

const safeRead = async <T>(
  code: string,
  message: string,
  read: () => Promise<T>,
  gaps: EvidenceGap[],
): Promise<T | null> => {
  try {
    return await read();
  } catch (error) {
    gaps.push(toGap(code, `${message}: ${error instanceof Error ? error.message : String(error)}`));
    return null;
  }
};

const averageNullableNumbers = (values: readonly (number | null | undefined)[]): number | null => {
  const numeric = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (numeric.length === 0) {
    return null;
  }
  return Math.round((numeric.reduce((sum, value) => sum + value, 0) / numeric.length) * 100) / 100;
};

const toShortRegion = (region: string | undefined): string | null => {
  if (region === undefined) {
    return null;
  }
  const normalized = region.replace(/\s+region$/i, "").trim();
  return normalized === "" ? null : normalized;
};

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> => {
  return typeof value === "object" && value !== null && !Array.isArray(value);
};

const NON_METRIC_NUMERIC_KEYS = new Set([
  "preliminary",
]);

const METRIC_LABEL_OVERRIDES: Readonly<Record<string, string>> = {
  sora: "SORA",
  sora_1m: "1M SORA",
  sora_3m: "3M SORA",
  sora_6m: "6M SORA",
  sor_average: "SOR Average",
  total_deposits: "Total deposits",
  total_loans: "Total loans",
  total_assets: "Total assets",
  resident_non_bank: "Resident non-bank deposits",
  resident_deposits: "Resident deposits",
  dbd_deposit: "DBU deposits",
};

type MacroDatasetIntent = "gdp" | "cpi";

type DatasetCandidate = Readonly<{
  id: string;
  title?: string | undefined;
  subject?: string | undefined;
  topic?: string | undefined;
  frequency?: string | undefined;
  theme?: string | undefined;
}>;

const isMeaningfulMetricKey = (key: string): boolean => {
  return !NON_METRIC_NUMERIC_KEYS.has(key.trim().toLowerCase());
};

const formatMetricLabel = (key: string): string => {
  return METRIC_LABEL_OVERRIDES[key] ?? key
    .split("_")
    .filter((part) => part !== "")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};

const getMacroDatasetText = (dataset: DatasetCandidate): Readonly<{
  title: string;
  topic: string;
  subject: string;
  combined: string;
}> => {
  const title = (dataset.title ?? "").toLowerCase();
  const topic = (dataset.topic ?? "").toLowerCase();
  const subject = (dataset.subject ?? "").toLowerCase();
  const combined = [title, topic, subject, (dataset.theme ?? "").toLowerCase()]
    .filter((part) => part !== "")
    .join(" ");

  return { title, topic, subject, combined };
};

const scoreMacroDataset = (
  dataset: DatasetCandidate,
  intent: MacroDatasetIntent,
): number => {
  const includeTerms = intent === "gdp"
    ? ["gross domestic product", "gdp", "national accounts"]
    : ["consumer price index", "cpi", "inflation", "prices"];
  const excludeTerms = intent === "gdp"
    ? ["consumer price index", "cpi", "inflation"]
    : ["gross domestic product", "gdp"];
  const { title, topic, subject, combined } = getMacroDatasetText(dataset);

  if (excludeTerms.some((term) => combined.includes(term))) {
    return -1;
  }

  let score = 0;
  for (const term of includeTerms) {
    if (title.includes(term)) {
      score += 4;
      continue;
    }
    if (topic.includes(term)) {
      score += 3;
      continue;
    }
    if (subject.includes(term)) {
      score += 2;
      continue;
    }
    if (combined.includes(term)) {
      score += 1;
    }
  }

  return score;
};

const rankMacroDatasets = (
  datasets: readonly DatasetCandidate[] | null | undefined,
  intent: MacroDatasetIntent,
): readonly DatasetCandidate[] => {
  if (!Array.isArray(datasets)) {
    return [];
  }

  return datasets
    .map((dataset) => ({
      dataset,
      score: scoreMacroDataset(dataset, intent),
    }))
    .filter((candidate) => candidate.score > 0)
    .sort((left, right) =>
      right.score - left.score
      || left.dataset.id.localeCompare(right.dataset.id)
      || (left.dataset.title ?? "").localeCompare(right.dataset.title ?? ""),
    )
    .map((candidate) => candidate.dataset);
};

const findFirstNumericField = (
  record: Readonly<Record<string, unknown>> | undefined,
): { key: string; value: number } | null => {
  if (record === undefined) {
    return null;
  }

  for (const [key, value] of Object.entries(record)) {
    if (key === "date" || !isMeaningfulMetricKey(key)) {
      continue;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return { key, value };
    }
  }
  return null;
};

const getFirstTimestamp = (
  value: unknown,
  fields: readonly string[],
): string | null => {
  const rows = Array.isArray(value) ? value : [value];
  for (const row of rows) {
    if (!isRecord(row)) {
      continue;
    }
    for (const field of fields) {
      const candidate = row[field];
      if (typeof candidate === "string" && candidate.trim() !== "") {
        return candidate;
      }
    }
  }
  return null;
};

const getFirstBusArrivalTimestamp = (value: unknown): string | null => {
  if (!Array.isArray(value)) {
    return null;
  }
  for (const row of value) {
    if (!isRecord(row)) {
      continue;
    }
    const arrivals = row["arrivals"];
    if (!Array.isArray(arrivals)) {
      continue;
    }
    for (const arrival of arrivals) {
      if (!isRecord(arrival)) {
        continue;
      }
      const estimatedArrival = arrival["estimatedArrival"];
      if (typeof estimatedArrival === "string" && estimatedArrival.trim() !== "") {
        return estimatedArrival;
      }
    }
  }
  return null;
};

const buildTransportFocus = (
  busStopCode: string | undefined,
  serviceNo: string | undefined,
): string => {
  if (busStopCode === undefined) {
    return "network-wide";
  }
  return serviceNo === undefined
    ? `bus stop ${busStopCode}`
    : `bus stop ${busStopCode} service ${serviceNo}`;
};

const getTransportOpsLevel = (params: Readonly<{ busStopCode?: string | undefined }>, counts: Readonly<{
  trainSignals: number;
  trafficSignals: number;
}>, nextArrival: string | null): "disrupted" | "advisory" | "unknown" | "normal" => {
  if (counts.trainSignals > 0) {
    return "disrupted";
  }
  if (counts.trafficSignals > 0) {
    return "advisory";
  }
  if (params.busStopCode !== undefined && nextArrival === null) {
    return "unknown";
  }
  return "normal";
};

const buildTransportHeadline = (
  level: "disrupted" | "advisory" | "unknown" | "normal",
  focus: string,
  counts: Readonly<{
    trainAlerts: number;
    trainMessages: number;
    trafficSignals: number;
  }>,
  primaryTrainLine: string | null,
  primaryIncidentType: string | null,
): string => {
  if (level === "disrupted") {
    return primaryTrainLine === null
      ? `Train disruptions reported for ${focus}.`
      : `Train disruptions reported on ${primaryTrainLine} for ${focus}.`;
  }
  if (level === "advisory") {
    return primaryIncidentType === null
      ? `Traffic advisory: ${counts.trafficSignals} incident(s) reported for ${focus}.`
      : `Traffic advisory: ${counts.trafficSignals} incident(s) including ${primaryIncidentType} for ${focus}.`;
  }
  if (level === "unknown") {
    return `No current bus ETA available for ${focus}, and no broader transport signals are active.`;
  }
  return `No active train or traffic disruptions detected for ${focus}.`;
};

const getTransportCoverage = (
  busStopCode: string | undefined,
  busArrivals: readonly Readonly<Record<string, unknown>>[] | null,
  nextArrival: string | null,
  trainAlerts: Readonly<{ alerts: readonly Readonly<Record<string, unknown>>[]; messages: readonly Readonly<Record<string, unknown>>[] }> | null,
  trafficIncidents: readonly Readonly<Record<string, unknown>>[] | null,
): {
  busCoverage: "not_requested" | "available" | "missing" | "unavailable";
  trainCoverage: "clear" | "alerts_active" | "unavailable";
  trafficCoverage: "clear" | "incidents_active" | "unavailable";
} => {
  const busCoverage =
    busStopCode === undefined
      ? "not_requested"
      : busArrivals === null
        ? "unavailable"
        : nextArrival !== null
          ? "available"
          : "missing";
  const trainCoverage =
    trainAlerts === null
      ? "unavailable"
      : trainAlerts.alerts.length + trainAlerts.messages.length > 0
        ? "alerts_active"
        : "clear";
  const trafficCoverage =
    trafficIncidents === null
      ? "unavailable"
      : trafficIncidents.length > 0
        ? "incidents_active"
        : "clear";

  return { busCoverage, trainCoverage, trafficCoverage };
};

const buildTransportSignals = (
  params: Readonly<{ busStopCode?: string | undefined; serviceNo?: string | undefined }>,
  nextArrival: string | null,
  counts: Readonly<{
    trainAlerts: number;
    trainMessages: number;
    trafficSignals: number;
  }>,
  primaryTrainLine: string | null,
  primaryIncidentType: string | null,
  coverage: Readonly<{
    busCoverage: string;
    trainCoverage: string;
    trafficCoverage: string;
  }>,
): readonly Readonly<Record<string, unknown>>[] => {
  const signals: Readonly<Record<string, unknown>>[] = [];
  const focus = buildTransportFocus(params.busStopCode, params.serviceNo);

  if (params.busStopCode !== undefined) {
    signals.push({
      source: "bus",
      level: nextArrival === null ? "unknown" : "normal",
      headline: nextArrival === null
        ? `No current bus ETA available for ${focus}.`
        : `Next bus ETA for ${focus} is ${nextArrival}.`,
      coverage: coverage.busCoverage,
    });
  }

  signals.push({
    source: "train",
    level: counts.trainAlerts + counts.trainMessages > 0 ? "disrupted" : coverage.trainCoverage === "unavailable" ? "unknown" : "normal",
    headline:
      counts.trainAlerts + counts.trainMessages > 0
        ? primaryTrainLine === null
          ? `${counts.trainAlerts} train alert(s) and ${counts.trainMessages} message(s) reported.`
          : `${counts.trainAlerts} train alert(s) and ${counts.trainMessages} message(s) reported on ${primaryTrainLine}.`
        : "No active train alerts reported.",
    coverage: coverage.trainCoverage,
  });

  signals.push({
    source: "traffic",
    level: counts.trafficSignals > 0 ? "advisory" : coverage.trafficCoverage === "unavailable" ? "unknown" : "normal",
    headline:
      counts.trafficSignals > 0
        ? primaryIncidentType === null
          ? `${counts.trafficSignals} traffic incident(s) reported.`
          : `${counts.trafficSignals} traffic incident(s) reported, including ${primaryIncidentType}.`
        : "No active traffic incidents reported.",
    coverage: coverage.trafficCoverage,
  });

  return signals;
};

const buildTransportNextChecks = (
  params: Readonly<{ busStopCode?: string | undefined; serviceNo?: string | undefined }>,
): readonly Readonly<Record<string, unknown>>[] => {
  const checks: Readonly<Record<string, unknown>>[] = [];
  if (params.busStopCode !== undefined) {
    checks.push({
      tool: "sg_lta_bus_arrivals",
      reason: "Inspect stop-level bus arrivals for the current transport focus.",
      input: {
        busStopCode: params.busStopCode,
        ...(params.serviceNo === undefined ? {} : { serviceNo: params.serviceNo }),
      },
    });
  }
  checks.push({
    tool: "sg_lta_train_alerts",
    reason: "Inspect network-wide train service alerts and operator messages.",
    input: {},
  });
  checks.push({
    tool: "sg_lta_traffic_incidents",
    reason: "Inspect live traffic incidents across Singapore.",
    input: {},
  });
  return checks;
};

const FORECAST_CAUTION_PATTERN = /\b(thunder|thundery|storm|heavy[\s-]*rain)\b/i;
const FORECAST_WATCH_PATTERN = /\b(rain|showers?)\b/i;

const getForecastRisk = (forecast: string | null | undefined): "caution" | "watch" | "clear" | "unknown" => {
  if (forecast === null || forecast === undefined || forecast.trim() === "") {
    return "unknown";
  }
  if (FORECAST_CAUTION_PATTERN.test(forecast)) {
    return "caution";
  }
  if (FORECAST_WATCH_PATTERN.test(forecast)) {
    return "watch";
  }
  return "clear";
};

const getAirQualityBand = (psi24h: number | null | undefined): "caution" | "watch" | "clear" | "unknown" => {
  if (typeof psi24h !== "number" || !Number.isFinite(psi24h)) {
    return "unknown";
  }
  if (psi24h > 100) {
    return "caution";
  }
  if (psi24h >= 51) {
    return "watch";
  }
  return "clear";
};

const getRainfallBand = (rainfall: number | null | undefined): "caution" | "watch" | "clear" | "unknown" => {
  if (typeof rainfall !== "number" || !Number.isFinite(rainfall)) {
    return "unknown";
  }
  if (rainfall >= 10) {
    return "caution";
  }
  if (rainfall > 0) {
    return "watch";
  }
  return "clear";
};

const buildEnvironmentScopeLabel = (
  focusArea: string | null,
  focusRegion: string | null,
  focusStation: string | null,
): string => {
  const scope = [
    focusArea === null ? null : `area ${focusArea}`,
    focusRegion === null ? null : `region ${focusRegion}`,
    focusStation === null ? null : `station ${focusStation}`,
  ].filter((value): value is string => value !== null);

  return scope.length === 0 ? "the requested scope" : scope.join(", ");
};

const getEnvironmentOpsLevel = (thresholds: Readonly<{
  forecastRisk: "caution" | "watch" | "clear" | "unknown";
  airQualityBand: "caution" | "watch" | "clear" | "unknown";
  rainfallBand: "caution" | "watch" | "clear" | "unknown";
}>): "caution" | "watch" | "clear" | "unknown" => {
  const bands = Object.values(thresholds);
  if (bands.includes("caution")) {
    return "caution";
  }
  if (bands.includes("watch")) {
    return "watch";
  }
  if (bands.includes("clear")) {
    return "clear";
  }
  return "unknown";
};

const buildEnvironmentHeadline = (
  level: "caution" | "watch" | "clear" | "unknown",
  focusArea: string | null,
  focusRegion: string | null,
  focusStation: string | null,
): string => {
  const scopeLabel = buildEnvironmentScopeLabel(focusArea, focusRegion, focusStation);
  if (level === "caution") {
    return `Environmental caution signals detected for ${scopeLabel}.`;
  }
  if (level === "watch") {
    return `Environmental watch signals detected for ${scopeLabel}.`;
  }
  if (level === "clear") {
    return `Current environmental signals are clear for ${scopeLabel}.`;
  }
  return `No current environmental signals are available for ${scopeLabel}.`;
};

const buildEnvironmentSignals = (
  primaryForecast: Readonly<Record<string, unknown>> | undefined,
  primaryAirQuality: Readonly<Record<string, unknown>> | undefined,
  primaryRainfall: Readonly<Record<string, unknown>> | undefined,
  thresholds: Readonly<{
    forecastRisk: "caution" | "watch" | "clear" | "unknown";
    airQualityBand: "caution" | "watch" | "clear" | "unknown";
    rainfallBand: "caution" | "watch" | "clear" | "unknown";
  }>,
): readonly Readonly<Record<string, unknown>>[] => {
  const signals: Readonly<Record<string, unknown>>[] = [];

  if (primaryForecast !== undefined) {
    signals.push({
      source: "forecast",
      level: thresholds.forecastRisk,
      headline: `Forecast ${String(primaryForecast["forecast"] ?? "")} for ${String(primaryForecast["area"] ?? "the requested area")}.`,
      input: primaryForecast["forecast"] ?? null,
    });
  }

  if (primaryAirQuality !== undefined) {
    signals.push({
      source: "air_quality",
      level: thresholds.airQualityBand,
      headline: `PSI 24h is ${String(primaryAirQuality["psi24h"] ?? "unknown")} for ${String(primaryAirQuality["region"] ?? "the requested region")}.`,
      input: primaryAirQuality["psi24h"] ?? null,
    });
  }

  if (primaryRainfall !== undefined) {
    signals.push({
      source: "rainfall",
      level: thresholds.rainfallBand,
      headline: `Rainfall is ${String(primaryRainfall["value"] ?? "unknown")} ${String(primaryRainfall["unit"] ?? "")}`.trim()
        + ` at ${String(primaryRainfall["stationName"] ?? primaryRainfall["stationId"] ?? "the requested station")}.`,
      input: primaryRainfall["value"] ?? null,
    });
  }

  return signals;
};

const buildEnvironmentNextChecks = (
  params: Readonly<{
    area?: string | undefined;
    region?: string | undefined;
    stationId?: string | undefined;
    date?: string | undefined;
  }>,
  resolved: Readonly<{
    focusArea: string | null;
    focusRegion: string | null;
    stationId: string | null;
  }>,
): readonly Readonly<Record<string, unknown>>[] => {
  return [
    {
      tool: "sg_nea_forecast_2hr",
      reason: "Inspect the focused 2-hour forecast directly.",
      input: {
        ...(resolved.focusArea === null ? params.area === undefined ? {} : { area: params.area } : { area: resolved.focusArea }),
        ...(params.date === undefined ? {} : { date: params.date }),
      },
    },
    {
      tool: "sg_nea_air_quality",
      reason: "Inspect the focused air-quality reading directly.",
      input: {
        ...(resolved.focusRegion === null ? params.region === undefined ? {} : { region: params.region } : { region: resolved.focusRegion }),
        ...(params.date === undefined ? {} : { date: params.date }),
      },
    },
    {
      tool: "sg_nea_rainfall",
      reason: "Inspect the focused rainfall reading directly.",
      input: {
        ...(resolved.stationId === null ? params.stationId === undefined ? {} : { stationId: params.stationId } : { stationId: resolved.stationId }),
        ...(params.date === undefined ? {} : { date: params.date }),
      },
    },
  ];
};

const toProvenance = (
  source: string,
  tool: string,
  coverage: string,
  authRequired: boolean,
  recordCount: number,
): BriefProvenanceItem => ({
  source,
  tool,
  coverage,
  authRequired,
  recordCount,
});

const toFreshness = (
  source: string,
  observedAt: string,
  upstreamTimestamp: string | null,
): BriefFreshnessItem => ({
  source,
  observedAt,
  upstreamTimestamp,
});

const buildBusinessRiskFlags = (
  params: Readonly<{ entityName?: string | undefined; uen?: string | undefined }>,
  acra: readonly Readonly<Record<string, unknown>>[],
  builders: readonly Readonly<Record<string, unknown>>[],
  contractors: readonly Readonly<Record<string, unknown>>[],
): readonly RiskFlag[] => {
  const flags: RiskFlag[] = [];
  const primary = acra[0];
  if (primary !== undefined) {
    const status = String(primary["entityStatusDescription"] ?? "").toLowerCase();
    if (status !== "" && status !== "live" && status !== "registered") {
      flags.push({ code: "ENTITY_NOT_ACTIVE", severity: "high", message: `Entity status is "${primary["entityStatusDescription"]}", not Live or Registered.`, source: "ACRA" });
    }
  }
  if ((params.entityName !== undefined || params.uen !== undefined) && acra.length === 0) {
    flags.push({ code: "NO_ACRA_MATCH", severity: "high", message: "No ACRA entity matched the provided identifier.", source: "ACRA" });
  }
  for (const b of builders) {
    const expiry = b["expiryDate"];
    if (typeof expiry === "string" && expiry.trim() !== "") {
      const expiryDate = new Date(expiry);
      if (!isNaN(expiryDate.getTime()) && expiryDate < new Date()) {
        flags.push({ code: "BUILDER_LICENSE_EXPIRED", severity: "high", message: `Builder license expired on ${expiry}.`, source: "BCA" });
      }
    }
  }
  for (const c of contractors) {
    const expiry = c["expiryDate"];
    if (typeof expiry === "string" && expiry.trim() !== "") {
      const expiryDate = new Date(expiry);
      if (!isNaN(expiryDate.getTime()) && expiryDate < new Date()) {
        flags.push({ code: "CONTRACTOR_EXPIRED", severity: "medium", message: `Contractor registration expired on ${expiry}.`, source: "BCA" });
      }
    }
  }
  return flags;
};

const buildBusinessMatchConfidence = (
  params: Readonly<{ entityName?: string | undefined; uen?: string | undefined; salespersonName?: string | undefined; registrationNo?: string | undefined; estateAgentName?: string | undefined; estateAgentLicenseNo?: string | undefined }>,
  acra: readonly Readonly<Record<string, unknown>>[],
  builders: readonly Readonly<Record<string, unknown>>[],
  contractors: readonly Readonly<Record<string, unknown>>[],
  salespersons: readonly Readonly<Record<string, unknown>>[],
): readonly MatchConfidence[] => {
  const matches: MatchConfidence[] = [];
  if (params.entityName !== undefined || params.uen !== undefined) {
    const hasExactUen = params.uen !== undefined && acra.some((r) => String(r["uen"]).toUpperCase() === params.uen!.toUpperCase());
    matches.push({
      source: "ACRA",
      confidence: acra.length === 0 ? "no-match" : hasExactUen ? "exact" : "name-fuzzy",
      matchedOn: hasExactUen ? "uen" : acra.length > 0 ? "entityName" : null,
    });
  }
  if (params.entityName !== undefined || params.uen !== undefined) {
    matches.push({
      source: "BCA licensed builders",
      confidence: builders.length === 0 ? "no-match" : params.uen !== undefined ? "exact" : "name-fuzzy",
      matchedOn: builders.length === 0 ? null : params.uen !== undefined ? "uenNo" : "companyName",
    });
    matches.push({
      source: "BCA registered contractors",
      confidence: contractors.length === 0 ? "no-match" : params.uen !== undefined ? "exact" : "name-fuzzy",
      matchedOn: contractors.length === 0 ? null : params.uen !== undefined ? "uenNo" : "companyName",
    });
  }
  if (params.salespersonName !== undefined || params.registrationNo !== undefined || params.estateAgentName !== undefined || params.estateAgentLicenseNo !== undefined) {
    const hasExactReg = params.registrationNo !== undefined && salespersons.length > 0;
    const hasExactLic = params.estateAgentLicenseNo !== undefined && salespersons.length > 0;
    matches.push({
      source: "CEA",
      confidence: salespersons.length === 0 ? "no-match" : (hasExactReg || hasExactLic) ? "exact" : "name-fuzzy",
      matchedOn: salespersons.length === 0 ? null : hasExactReg ? "registrationNo" : hasExactLic ? "estateAgentLicenseNo" : "name",
    });
  }
  return matches;
};

const buildBusinessNextChecks = (
  params: Readonly<{ entityName?: string | undefined; uen?: string | undefined }>,
): readonly NextCheck[] => {
  const checks: NextCheck[] = [];
  if (params.uen !== undefined) {
    checks.push({ tool: "sg_acra_entities", reason: "Retrieve full ACRA entity details for deeper officer and financial-year inspection.", input: { uen: params.uen } });
  }
  if (params.entityName !== undefined) {
    checks.push({ tool: "sg_bca_licensed_builders", reason: "Inspect all licensed-builder records for the entity.", input: { companyName: params.entityName } });
    checks.push({ tool: "sg_bca_registered_contractors", reason: "Inspect all registered-contractor records for the entity.", input: { companyName: params.entityName } });
  }
  checks.push({ tool: "sg_datagov_search", reason: "Search data.gov.sg for additional public records related to this entity.", input: { query: params.entityName ?? params.uen ?? "" } });
  return checks;
};

const buildBusinessLimits = (): readonly BriefLimit[] => [
  toLimit("EXACT_MATCH_ONLY", "Registry checks are exact-match oriented for company, UEN, salesperson, and estate-agent identifiers."),
  toLimit("NO_CORPORATE_GRAPH", "This dossier does not infer subsidiaries, shareholders, officers, or beneficial ownership relationships."),
  toLimit("PUBLIC_REGISTRY_SCOPE", "The brief only covers ACRA, BCA, and CEA public registry evidence exposed through the current direct tools."),
];

const medianSorted = (values: readonly number[]): number | null => {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? Math.round(((sorted[mid - 1]! + sorted[mid]!) / 2) * 100) / 100 : sorted[mid]!;
};

const computeTransactionRollup = (
  records: readonly Readonly<Record<string, unknown>>[] | null,
  priceField: string,
  dateField: string,
): Readonly<Record<string, unknown>> | null => {
  if (records === null || records.length === 0) return null;
  const prices = records.map((r) => Number(r[priceField])).filter((v) => Number.isFinite(v));
  const dates = records.map((r) => String(r[dateField] ?? "")).filter((d) => d !== "").sort();
  if (prices.length === 0) return null;
  return {
    count: prices.length,
    median: medianSorted(prices),
    min: Math.min(...prices),
    max: Math.max(...prices),
    average: Math.round((prices.reduce((s, v) => s + v, 0) / prices.length) * 100) / 100,
    latestMonth: dates[dates.length - 1] ?? null,
  };
};

const buildPropertyDealChecklist = (
  uraRollup: Readonly<Record<string, unknown>> | null,
  hdbRollup: Readonly<Record<string, unknown>> | null,
  planningArea: string | null,
  propertyType: string | undefined,
): readonly RiskFlag[] => {
  const flags: RiskFlag[] = [];
  if (uraRollup !== null) {
    const latest = uraRollup["latestMonth"];
    if (typeof latest === "string") {
      const months = (Date.now() - new Date(latest).getTime()) / (1000 * 60 * 60 * 24 * 30);
      if (months > 6) {
        flags.push({ code: "STALE_URA_DATA", severity: "medium", message: `Latest URA transaction is from ${latest}, more than 6 months ago.`, source: "URA" });
      }
    }
  } else if (planningArea !== null) {
    flags.push({ code: "NO_URA_TRANSACTIONS", severity: "low", message: "No URA private transactions found for this planning area.", source: "URA" });
  }
  if (propertyType === "residential" || propertyType === undefined) {
    if (hdbRollup === null && planningArea !== null) {
      flags.push({ code: "NO_HDB_CONTEXT", severity: "low", message: "No HDB resale context available for residential comparison.", source: "HDB" });
    }
  }
  if (planningArea === null) {
    flags.push({ code: "UNRESOLVED_LOCATION", severity: "high", message: "Location could not be resolved to a planning area.", source: "OneMap" });
  }
  return flags;
};

const buildPropertyNextChecks = (
  planningArea: string | null,
  postalCode: string | null,
  resolvedLat: number | null,
  resolvedLng: number | null,
): readonly NextCheck[] => {
  const checks: NextCheck[] = [];
  if (planningArea !== null) {
    checks.push({ tool: "sg_ura_property_transactions", reason: "Retrieve detailed URA transactions for deeper price analysis.", input: { propertyType: "residential", planningArea } });
    checks.push({ tool: "sg_hdb_resale_prices", reason: "Retrieve detailed HDB resale records for the planning area.", input: { town: planningArea } });
    checks.push({ tool: "sg_ura_dev_charges", reason: "Check development charges for the planning area.", input: { planningArea } });
  }
  if (resolvedLat !== null && resolvedLng !== null) {
    checks.push({ tool: "sg_onemap_reverse_geocode", reason: "Get full address details for the resolved location.", input: { lat: resolvedLat, lng: resolvedLng } });
  } else if (postalCode !== null) {
    checks.push({ tool: "sg_onemap_geocode", reason: "Geocode the postal code for detailed location data.", input: { searchVal: postalCode, returnGeom: true, getAddrDetails: true } });
  }
  return checks;
};

const buildPropertyLimits = (includeTransport: boolean, includeEnvironment: boolean): readonly BriefLimit[] => {
  const limits: BriefLimit[] = [
    toLimit("NOT_A_RECOMMENDATION", "This brief is bounded diligence context, not a valuation, investment score, or purchase recommendation."),
    toLimit("AREA_LEVEL_CONTEXT", "Property context is planning-area oriented and does not replace parcel-level legal or title checks."),
  ];
  if (!includeTransport) {
    limits.push(toLimit("TRANSPORT_NOT_INCLUDED", "Live transport context was not requested for this property brief."));
  }
  if (!includeEnvironment) {
    limits.push(toLimit("ENVIRONMENT_NOT_INCLUDED", "Live weather and air-quality context was not requested for this property brief."));
  }
  return limits;
};

const extractNamedMasMetric = (
  record: Readonly<Record<string, unknown>> | undefined,
  preferredKeys: readonly string[],
): { key: string; value: number } | null => {
  if (record === undefined) return null;
  for (const key of preferredKeys) {
    const v = record[key];
    if (typeof v === "number" && Number.isFinite(v) && isMeaningfulMetricKey(key)) return { key, value: v };
  }
  return findFirstNumericField(record);
};

const computeMasDelta = (
  records: readonly Readonly<Record<string, unknown>>[] | null,
  metricKey: string,
): number | null => {
  if (records === null || records.length < 2) return null;
  const latest = Number(records[0]?.[metricKey]);
  const prev = Number(records[1]?.[metricKey]);
  if (!Number.isFinite(latest) || !Number.isFinite(prev) || prev === 0) return null;
  return Math.round(((latest - prev) / Math.abs(prev)) * 10000) / 100;
};

const buildMacroNextChecks = (
  gdpTableId: string | null,
  cpiTableId: string | null,
): readonly NextCheck[] => {
  const checks: NextCheck[] = [];
  if (gdpTableId !== null) {
    checks.push({ tool: "sg_singstat_table", reason: "Retrieve full GDP table data for detailed analysis.", input: { tableId: gdpTableId } });
  }
  if (cpiTableId !== null) {
    checks.push({ tool: "sg_singstat_table", reason: "Retrieve full CPI table data for inflation analysis.", input: { tableId: cpiTableId } });
  }
  checks.push({ tool: "sg_singstat_search", reason: "Discover additional SingStat datasets for deeper macro analysis.", input: { keyword: "Singapore unemployment" } });
  return checks;
};

const buildMacroLimits = (): readonly BriefLimit[] => [
  toLimit("STARTER_SNAPSHOT", "This brief is a compact macro starter, not a full economic research note or narrative analysis."),
  toLimit("DATASET_ENTRYPOINTS_ONLY", "SingStat coverage is limited to bounded dataset discovery in this brief rather than full table extraction."),
  toLimit("NO_FORWARD_VIEW", "The brief reports current or requested historical values and does not forecast or interpret future macro conditions."),
];

const buildTransportLimits = (hasBusStopCode: boolean): readonly BriefLimit[] => {
  const limits: BriefLimit[] = [
    toLimit("SNAPSHOT_ONLY", "This brief summarizes current LTA operational conditions and does not predict delays or incident resolution time."),
    toLimit("NO_ROUTE_PLANNING", "Use sg_onemap_route for route planning; this brief only summarizes transport operations status."),
  ];
  if (!hasBusStopCode) {
    limits.push(toLimit("NO_STOP_LEVEL_ARRIVALS", "No specific bus stop was supplied, so stop-level arrival timings are not included."));
  }
  return limits;
};

const buildEnvironmentLimits = (hasArea: boolean, hasRegion: boolean, hasStation: boolean): readonly BriefLimit[] => {
  const limits: BriefLimit[] = [
    toLimit("LIVE_SNAPSHOT_ONLY", "This brief summarizes current NEA conditions and does not replace severe-weather alerts or long-range forecasting."),
  ];
  if (!hasArea) {
    limits.push(toLimit("NO_AREA_FILTER", "No specific forecast area was supplied, so the brief reports the first available forecast area summary."));
  }
  if (!hasRegion) {
    limits.push(toLimit("NO_REGION_FILTER", "No specific air-quality region was supplied, so the brief reports the first available regional reading."));
  }
  if (!hasStation) {
    limits.push(toLimit("NO_STATION_FILTER", "No rainfall station ID was supplied, so the brief reports the first available station reading."));
  }
  return limits;
};

export const handleBusinessDossier = async (
  params: Readonly<{
    entityName?: string | undefined;
    uen?: string | undefined;
    salespersonName?: string | undefined;
    registrationNo?: string | undefined;
    estateAgentName?: string | undefined;
    estateAgentLicenseNo?: string | undefined;
    classCode?: string | undefined;
    workhead?: string | undefined;
    grade?: string | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  const companyName = params.entityName;

  const [acraRecords, bcaLicensedBuilders, bcaRegisteredContractors, ceaSalespersons] = await Promise.all([
    params.entityName !== undefined || params.uen !== undefined
      ? safeRead(
          "ACRA_UNAVAILABLE",
          "ACRA lookup failed",
          () => getAcraEntities({ entityName: params.entityName, uen: params.uen, limit: 5 }),
          gaps,
        )
      : Promise.resolve(null),
    params.entityName !== undefined || params.uen !== undefined || params.classCode !== undefined
      ? safeRead(
          "BCA_BUILDERS_UNAVAILABLE",
          "BCA licensed-builder lookup failed",
          () => getBcaLicensedBuilders({
            companyName,
            uenNo: params.uen,
            classCode: params.classCode,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    params.entityName !== undefined || params.uen !== undefined || params.workhead !== undefined || params.grade !== undefined
      ? safeRead(
          "BCA_CONTRACTORS_UNAVAILABLE",
          "BCA registered-contractor lookup failed",
          () => getBcaRegisteredContractors({
            companyName,
            uenNo: params.uen,
            workhead: params.workhead,
            grade: params.grade,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    params.salespersonName !== undefined
      || params.registrationNo !== undefined
      || params.estateAgentName !== undefined
      || params.estateAgentLicenseNo !== undefined
      ? safeRead(
          "CEA_UNAVAILABLE",
          "CEA lookup failed",
          () => getCeaSalespersons({
            salespersonName: params.salespersonName,
            registrationNo: params.registrationNo,
            estateAgentName: params.estateAgentName,
            estateAgentLicenseNo: params.estateAgentLicenseNo,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
  ]);

  const acra = acraRecords ?? [];
  const builders = bcaLicensedBuilders ?? [];
  const contractors = bcaRegisteredContractors ?? [];
  const salespersons = ceaSalespersons ?? [];

  if ((params.entityName !== undefined || params.uen !== undefined) && acra.length === 0) {
    gaps.push(toGap("ACRA_NO_MATCH", "No exact ACRA entity matched the provided company name or UEN."));
  }
  if ((params.entityName !== undefined || params.uen !== undefined || params.classCode !== undefined) && builders.length === 0) {
    gaps.push(toGap("BCA_BUILDERS_NO_MATCH", "No licensed-builder record matched the provided company, UEN, or class code."));
  }
  if ((params.entityName !== undefined || params.uen !== undefined || params.workhead !== undefined || params.grade !== undefined) && contractors.length === 0) {
    gaps.push(toGap("BCA_CONTRACTORS_NO_MATCH", "No registered-contractor record matched the provided company, UEN, workhead, or grade."));
  }
  if ((params.salespersonName !== undefined || params.registrationNo !== undefined || params.estateAgentName !== undefined || params.estateAgentLicenseNo !== undefined) && salespersons.length === 0) {
    gaps.push(toGap("CEA_NO_MATCH", "No CEA salesperson or estate-agent record matched the provided identifier."));
  }

  const primaryAcra = acra[0];
  const primaryBuilder = builders[0];
  const primaryContractor = contractors[0];
  const primarySalesperson = salespersons[0];
  const riskFlags = buildBusinessRiskFlags(params, acra, builders, contractors);
  const matchConfidence = buildBusinessMatchConfidence(params, acra, builders, contractors, salespersons);
  const nextChecks = buildBusinessNextChecks(params);

  const payload: BriefArtifact = {
    title: "Business Dossier",
    summary: [
      { label: "Entity", value: primaryAcra?.entityName ?? params.entityName ?? null, source: "ACRA" },
      { label: "UEN", value: primaryAcra?.uen ?? params.uen ?? null, source: "ACRA" },
      { label: "Entity status", value: primaryAcra?.entityStatusDescription ?? null, source: "ACRA" },
      { label: "Licensed builder", value: primaryBuilder?.classCode ?? null, source: "BCA" },
      { label: "Registered contractor", value: primaryContractor?.workhead ?? null, source: "BCA" },
      { label: "Estate agent", value: primarySalesperson?.estateAgentName ?? params.estateAgentName ?? null, source: "CEA" },
    ],
    evidence: [
      { label: "ACRA matches", value: acra.length, source: "ACRA" },
      { label: "BCA licensed-builder matches", value: builders.length, source: "BCA" },
      { label: "BCA contractor matches", value: contractors.length, source: "BCA" },
      { label: "CEA matches", value: salespersons.length, source: "CEA" },
      { label: "Officer count", value: primaryAcra?.noOfOfficers ?? null, source: "ACRA" },
      { label: "Builder expiry", value: primaryBuilder?.expiryDate ?? null, source: "BCA" },
    ],
    records: {
      acra,
      bcaLicensedBuilders: builders,
      bcaRegisteredContractors: contractors,
      ceaSalespersons: salespersons,
    },
    gaps,
    provenance: [
      toProvenance("ACRA", "sg_acra_entities", "Exact-match company and UEN registry evidence.", false, acra.length),
      toProvenance("BCA", "sg_bca_licensed_builders", "Licensed-builder registry evidence for the named entity or class code.", false, builders.length),
      toProvenance("BCA", "sg_bca_registered_contractors", "Registered-contractor registry evidence for the named entity, workhead, or grade.", false, contractors.length),
      toProvenance("CEA", "sg_cea_salespersons", "Salesperson and estate-agent registry evidence for the supplied identifiers.", false, salespersons.length),
    ],
    freshness: [
      toFreshness("ACRA", observedAt, getFirstTimestamp(acra, ["annualReturnDate", "accountDueDate", "registrationIncorporationDate"])),
      toFreshness("BCA licensed builders", observedAt, getFirstTimestamp(builders, ["expiryDate"])),
      toFreshness("BCA registered contractors", observedAt, getFirstTimestamp(contractors, ["expiryDate"])),
      toFreshness("CEA", observedAt, getFirstTimestamp(salespersons, ["registrationEndDate", "registrationStartDate"])),
    ],
    limits: buildBusinessLimits(),
    riskFlags,
    matchConfidence,
    nextChecks,
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

export const handlePropertyBrief = async (
  params: Readonly<{
    planningArea?: string | undefined;
    postalCode?: string | undefined;
    address?: string | undefined;
    flatType?: string | undefined;
    propertyType?: "residential" | "commercial" | "industrial" | undefined;
    includeTransport?: boolean | undefined;
    includeEnvironment?: boolean | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  const includeEnvironment = params.includeEnvironment ?? true;
  const includeTransport = params.includeTransport ?? false;

  const geocodeResults =
    params.planningArea !== undefined
      ? null
      : await safeRead(
          "ONEMAP_GEOCODE_FAILED",
          "OneMap geocode failed",
          () => geocode(params.postalCode ?? params.address ?? "", 1),
          gaps,
        );

  const firstGeocode = geocodeResults?.[0] ?? null;
  if (params.planningArea === undefined && firstGeocode === null) {
    gaps.push(toGap("LOCATION_UNRESOLVED", "The supplied postal code or address did not resolve to a Singapore location."));
  }

  const planningRecords = await safeRead(
    "URA_PLANNING_FAILED",
    "URA planning-area lookup failed",
    () => lookupPlanningArea(
      params.planningArea !== undefined
        ? { planningArea: params.planningArea }
        : { lat: firstGeocode?.lat, lng: firstGeocode?.lng },
    ),
    gaps,
  );

  const planning = planningRecords?.[0];
  const planningArea = planning?.planningArea ?? params.planningArea ?? null;
  const region = toShortRegion(planning?.region);

  const uraTransactions = planningArea === null
    ? null
    : await safeRead(
        "URA_TRANSACTIONS_FAILED",
        "URA transaction lookup failed",
        () => getPropertyTransactions(params.propertyType ?? "residential", planningArea, undefined),
        gaps,
      );

  const hdbResale = planningArea === null || (params.propertyType !== undefined && params.propertyType !== "residential")
    ? null
    : await safeRead(
        "HDB_RESALE_FAILED",
        "HDB resale lookup failed",
        () => getHdbResalePrices({ town: planningArea, flatType: params.flatType, limit: 25 }),
        gaps,
      );

  const forecast = includeEnvironment && planningArea !== null
    ? await safeRead(
        "NEA_FORECAST_FAILED",
        "NEA forecast lookup failed",
        () => getForecast2Hr(planningArea),
        gaps,
      )
    : null;

  const airQuality = includeEnvironment && region !== null
    ? await safeRead(
        "NEA_AIR_QUALITY_FAILED",
        "NEA air-quality lookup failed",
        () => getAirQuality(region),
        gaps,
      )
    : null;

  const trainAlerts = includeTransport
    ? await safeRead(
        "LTA_TRAIN_ALERTS_FAILED",
        "LTA train-alert lookup failed",
        () => getTrainAlerts(),
        gaps,
      )
    : null;

  const trafficIncidents = includeTransport
    ? await safeRead(
        "LTA_TRAFFIC_FAILED",
        "LTA traffic-incident lookup failed",
        () => getTrafficIncidents(),
        gaps,
      )
    : null;

  const resaleAverage = averageNullableNumbers((hdbResale ?? []).map((row) => row.resalePrice));
  const privateAverage = averageNullableNumbers(
    (uraTransactions ?? []).map((row) => {
      const parsed = Number(row.price);
      return Number.isFinite(parsed) ? parsed : null;
    }),
  );
  const primaryForecast = forecast?.[0];
  const primaryAirQuality = airQuality?.[0];
  const uraRollup = computeTransactionRollup(
    uraTransactions as readonly Readonly<Record<string, unknown>>[] | null,
    "price", "contractDate",
  );
  const hdbRollup = computeTransactionRollup(
    hdbResale as readonly Readonly<Record<string, unknown>>[] | null,
    "resalePrice", "month",
  );
  const marketComparison = privateAverage !== null && resaleAverage !== null
    ? { privateAvg: privateAverage, hdbResaleAvg: resaleAverage, delta: Math.round((privateAverage - resaleAverage) * 100) / 100, ratio: Math.round((privateAverage / resaleAverage) * 100) / 100 }
    : null;
  const dealChecklist = buildPropertyDealChecklist(uraRollup, hdbRollup, planningArea, params.propertyType);
  const propertyNextChecks = buildPropertyNextChecks(planningArea, firstGeocode?.postal ?? params.postalCode ?? null, firstGeocode?.lat ?? null, firstGeocode?.lng ?? null);

  const payload: BriefArtifact = {
    title: "Property Brief",
    summary: [
      { label: "Resolved planning area", value: planningArea, source: "URA" },
      { label: "Region", value: region, source: "URA" },
      { label: "Resolved postal code", value: firstGeocode?.postal ?? params.postalCode ?? null, source: "OneMap" },
      { label: "Private transaction average", value: privateAverage, source: "URA" },
      { label: "Private transaction median", value: uraRollup?.["median"] as number | null ?? null, source: "URA" },
      { label: "HDB resale average", value: resaleAverage, source: "HDB" },
      { label: "HDB resale median", value: hdbRollup?.["median"] as number | null ?? null, source: "HDB" },
      { label: "Forecast", value: primaryForecast?.forecast ?? null, source: "NEA" },
      { label: "PSI 24h", value: primaryAirQuality?.psi24h ?? null, source: "NEA" },
    ],
    evidence: [
      { label: "URA transactions", value: uraTransactions?.length ?? 0, source: "URA" },
      { label: "HDB resale records", value: hdbResale?.length ?? 0, source: "HDB" },
      { label: "2-hour forecast rows", value: forecast?.length ?? 0, source: "NEA" },
      { label: "Air-quality rows", value: airQuality?.length ?? 0, source: "NEA" },
      { label: "Train alerts", value: trainAlerts?.alerts.length ?? 0, source: "LTA" },
      { label: "Traffic incidents", value: trafficIncidents?.length ?? 0, source: "LTA" },
    ],
    records: {
      geocode: firstGeocode === null ? [] : [firstGeocode],
      planningArea: planningRecords ?? [],
      uraTransactions: uraTransactions ?? [],
      uraRollup: uraRollup ?? {},
      hdbResale: hdbResale ?? [],
      hdbRollup: hdbRollup ?? {},
      marketComparison: marketComparison ?? {},
      forecast: forecast ?? [],
      airQuality: airQuality ?? [],
      trainAlerts: trainAlerts?.alerts ?? [],
      trainAlertMessages: trainAlerts?.messages ?? [],
      trafficIncidents: trafficIncidents ?? [],
    },
    gaps,
    provenance: [
      toProvenance("OneMap", "sg_onemap_geocode", "Postal-code or address resolution into a Singapore geocode candidate.", true, firstGeocode === null ? 0 : 1),
      toProvenance("URA", "sg_ura_planning_area", "Planning-area resolution for the requested location.", true, planningRecords?.length ?? 0),
      toProvenance("URA", "sg_ura_property_transactions", "Private market transaction context for the resolved planning area.", true, uraTransactions?.length ?? 0),
      toProvenance("HDB", "sg_hdb_resale_prices", "Curated HDB resale market context for the resolved planning area.", false, hdbResale?.length ?? 0),
      ...(includeEnvironment
        ? [
            toProvenance("NEA", "sg_nea_forecast_2hr", "2-hour forecast coverage for the resolved planning area.", false, forecast?.length ?? 0),
            toProvenance("NEA", "sg_nea_air_quality", "Regional air-quality coverage for the resolved region.", false, airQuality?.length ?? 0),
          ]
        : []),
      ...(includeTransport
        ? [
            toProvenance("LTA", "sg_lta_train_alerts", "Network-wide train service alert coverage.", true, (trainAlerts?.alerts.length ?? 0) + (trainAlerts?.messages.length ?? 0)),
            toProvenance("LTA", "sg_lta_traffic_incidents", "Live traffic incident coverage across Singapore.", true, trafficIncidents?.length ?? 0),
          ]
        : []),
    ],
    freshness: [
      toFreshness("OneMap geocode", observedAt, null),
      toFreshness("URA planning area", observedAt, null),
      toFreshness("URA transactions", observedAt, getFirstTimestamp(uraTransactions, ["contractDate", "date"])),
      toFreshness("HDB resale", observedAt, getFirstTimestamp(hdbResale, ["month"])),
      ...(includeEnvironment
        ? [
            toFreshness("NEA forecast", observedAt, getFirstTimestamp(forecast, ["updatedAt", "validFrom"])),
            toFreshness("NEA air quality", observedAt, getFirstTimestamp(airQuality, ["updatedAt"])),
          ]
        : []),
      ...(includeTransport
        ? [
            toFreshness("LTA train alerts", observedAt, getFirstTimestamp(trainAlerts?.messages, ["createdDate"])),
            toFreshness("LTA traffic incidents", observedAt, null),
          ]
        : []),
    ],
    limits: buildPropertyLimits(includeTransport, includeEnvironment),
    riskFlags: dealChecklist,
    nextChecks: propertyNextChecks,
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

export const handleMacroBrief = async (
  params: Readonly<{
    currency?: string | undefined;
    date?: string | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  const currency = (params.currency ?? "USD").toUpperCase();

  const [exchangeRates, interestRates, financialStats, gdpDatasets, cpiDatasets] = await Promise.all([
    safeRead(
      "MAS_EXCHANGE_FAILED",
      "MAS exchange-rate lookup failed",
      () => fetchNormalizedMasRecords(MasDataset.EXCHANGE_RATES, {
        ...(params.date === undefined ? {} : { date: params.date }),
        ...(params.startDate === undefined ? {} : { startDate: params.startDate }),
        ...(params.endDate === undefined ? {} : { endDate: params.endDate }),
      }),
      gaps,
    ),
    safeRead(
      "MAS_SORA_FAILED",
      "MAS SORA lookup failed",
      () => fetchNormalizedMasRecords(MasDataset.INTEREST_RATES_SORA, {
        ...(params.date === undefined ? {} : { date: params.date }),
        ...(params.startDate === undefined ? {} : { startDate: params.startDate }),
        ...(params.endDate === undefined ? {} : { endDate: params.endDate }),
      }),
      gaps,
    ),
    safeRead(
      "MAS_BANKING_FAILED",
      "MAS banking-stat lookup failed",
      () => fetchNormalizedMasRecords(MasDataset.BANKING_STATS, {
        ...(params.date === undefined ? {} : { date: params.date }),
        ...(params.startDate === undefined ? {} : { startDate: params.startDate }),
        ...(params.endDate === undefined ? {} : { endDate: params.endDate }),
      }),
      gaps,
    ),
    safeRead(
      "SINGSTAT_GDP_FAILED",
      "SingStat GDP dataset discovery failed",
      () => searchSingStatDatasets("Singapore GDP", 3),
      gaps,
    ),
    safeRead(
      "SINGSTAT_CPI_FAILED",
      "SingStat CPI dataset discovery failed",
      () => searchSingStatDatasets("Singapore CPI inflation", 3),
      gaps,
    ),
  ]);
  const rankedGdpDatasets = rankMacroDatasets(gdpDatasets, "gdp");
  const rankedCpiDatasets = rankMacroDatasets(cpiDatasets, "cpi");

  if (Array.isArray(gdpDatasets) && gdpDatasets.length > 0 && rankedGdpDatasets.length === 0) {
    gaps.push({
      code: "SINGSTAT_GDP_NO_RELEVANT_DATASET",
      message: "SingStat GDP search returned datasets, but none matched GDP-specific criteria.",
    });
  }
  if (Array.isArray(cpiDatasets) && cpiDatasets.length > 0 && rankedCpiDatasets.length === 0) {
    gaps.push({
      code: "SINGSTAT_CPI_NO_RELEVANT_DATASET",
      message: "SingStat CPI search returned datasets, but none matched CPI-specific criteria.",
    });
  }

  const latestExchange = exchangeRates?.[0];
  const latestInterest = interestRates?.[0];
  const latestBanking = financialStats?.[0];
  const exchangeKey = `${currency.toLowerCase()}_sgd`;
  const exchangeValue = latestExchange?.[exchangeKey]
    ?? latestExchange?.[`${currency.toLowerCase()}_sgd_100`]
    ?? null;
  const soraMetric = extractNamedMasMetric(latestInterest, ["sora", "sora_1m", "sora_3m", "sora_6m", "sor_average"]);
  const bankingMetric = extractNamedMasMetric(latestBanking, ["total_deposits", "total_loans", "total_assets", "dbd_deposit"]);
  const fxDelta = computeMasDelta(exchangeRates, exchangeKey);
  const soraDelta = soraMetric !== null ? computeMasDelta(interestRates, soraMetric.key) : null;
  const gdpTableId = rankedGdpDatasets[0]?.id ?? null;
  const cpiTableId = rankedCpiDatasets[0]?.id ?? null;
  const macroNextChecks = buildMacroNextChecks(gdpTableId, cpiTableId);

  const payload: BriefArtifact = {
    title: "Macro Brief",
    summary: [
      { label: `${currency}/SGD`, value: typeof exchangeValue === "number" ? exchangeValue : exchangeValue as string | null, source: "MAS" },
      { label: "FX date", value: typeof latestExchange?.["date"] === "string" ? latestExchange["date"] : null, source: "MAS" },
      { label: "FX period delta %", value: fxDelta, source: "MAS" },
      { label: soraMetric === null ? "SORA" : formatMetricLabel(soraMetric.key), value: soraMetric?.value ?? null, source: "MAS" },
      { label: "SORA period delta %", value: soraDelta, source: "MAS" },
      { label: bankingMetric === null ? "Banking metric" : formatMetricLabel(bankingMetric.key), value: bankingMetric?.value ?? null, source: "MAS" },
      { label: "GDP dataset", value: rankedGdpDatasets[0]?.title ?? null, source: "SingStat" },
      { label: "GDP table ID", value: gdpTableId, source: "SingStat" },
      { label: "CPI dataset", value: rankedCpiDatasets[0]?.title ?? null, source: "SingStat" },
      { label: "CPI table ID", value: cpiTableId, source: "SingStat" },
    ],
    evidence: [
      { label: "FX rows", value: exchangeRates?.length ?? 0, source: "MAS" },
      { label: "SORA rows", value: interestRates?.length ?? 0, source: "MAS" },
      { label: "Banking rows", value: financialStats?.length ?? 0, source: "MAS" },
      { label: "GDP candidates", value: rankedGdpDatasets.length, source: "SingStat" },
      { label: "CPI candidates", value: rankedCpiDatasets.length, source: "SingStat" },
      { label: "Primary SORA key", value: soraMetric?.key ?? null, source: "MAS" },
      { label: "Primary banking key", value: bankingMetric?.key ?? null, source: "MAS" },
    ],
    records: {
      exchangeRates: exchangeRates ?? [],
      interestRates: interestRates ?? [],
      financialStats: financialStats ?? [],
      gdpDatasets: rankedGdpDatasets,
      cpiDatasets: rankedCpiDatasets,
    },
    gaps,
    provenance: [
      toProvenance("MAS", "sg_mas_exchange_rates", "Exchange-rate coverage for the requested currency and date range.", false, exchangeRates?.length ?? 0),
      toProvenance("MAS", "sg_mas_interest_rates", "SORA interest-rate coverage for the requested date range.", false, interestRates?.length ?? 0),
      toProvenance("MAS", "sg_mas_financial_stats", "Banking-statistics coverage for the requested date range.", false, financialStats?.length ?? 0),
      toProvenance("SingStat", "sg_singstat_search", "Bounded dataset discovery for GDP and CPI entrypoints.", false, (gdpDatasets?.length ?? 0) + (cpiDatasets?.length ?? 0)),
    ],
    freshness: [
      toFreshness("MAS exchange rates", observedAt, getFirstTimestamp(exchangeRates, ["date"])),
      toFreshness("MAS interest rates", observedAt, getFirstTimestamp(interestRates, ["date"])),
      toFreshness("MAS banking stats", observedAt, getFirstTimestamp(financialStats, ["date"])),
      toFreshness("SingStat GDP search", observedAt, null),
      toFreshness("SingStat CPI search", observedAt, null),
    ],
    limits: buildMacroLimits(),
    nextChecks: macroNextChecks,
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

export const handleTransportBrief = async (
  params: Readonly<{
    busStopCode?: string | undefined;
    serviceNo?: string | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];

  const [busArrivals, trainAlerts, trafficIncidents] = await Promise.all([
    params.busStopCode === undefined
      ? Promise.resolve(null)
      : safeRead(
          "LTA_BUS_ARRIVALS_FAILED",
          "LTA bus-arrival lookup failed",
          () => getBusArrivals(params.busStopCode!, params.serviceNo),
          gaps,
        ),
    safeRead(
      "LTA_TRAIN_ALERTS_FAILED",
      "LTA train-alert lookup failed",
      () => getTrainAlerts(),
      gaps,
    ),
    safeRead(
      "LTA_TRAFFIC_FAILED",
      "LTA traffic-incident lookup failed",
      () => getTrafficIncidents(),
      gaps,
    ),
  ]);

  const nextArrival = getFirstBusArrivalTimestamp(busArrivals);
  const primaryTrainLine = trainAlerts?.alerts[0]?.line ?? null;
  const primaryIncidentType = trafficIncidents?.[0]?.type ?? null;
  const focus = buildTransportFocus(params.busStopCode, params.serviceNo);

  // stop summary: service count + avg wait
  const stopSummary = params.busStopCode !== undefined && busArrivals !== null ? (() => {
    const serviceCount = busArrivals.length;
    const waitMins: number[] = [];
    for (const svc of busArrivals) {
      const arrivals = (svc as Readonly<Record<string, unknown>>)["arrivals"];
      if (Array.isArray(arrivals) && arrivals.length > 0) {
        const first = arrivals[0] as Readonly<Record<string, unknown>> | undefined;
        const eta = first?.["estimatedArrival"];
        if (typeof eta === "string") {
          const diff = (new Date(eta).getTime() - Date.now()) / 60000;
          if (Number.isFinite(diff) && diff >= 0) waitMins.push(Math.round(diff * 10) / 10);
        }
      }
    }
    return { serviceCount, avgWaitMinutes: waitMins.length > 0 ? Math.round((waitMins.reduce((s, v) => s + v, 0) / waitMins.length) * 10) / 10 : null };
  })() : null;

  // incident summary: count by type
  const incidentSummary = trafficIncidents !== null && trafficIncidents.length > 0 ? (() => {
    const byType: Record<string, number> = {};
    for (const inc of trafficIncidents) {
      const t = String((inc as Readonly<Record<string, unknown>>)["type"] ?? "unknown");
      byType[t] = (byType[t] ?? 0) + 1;
    }
    return { total: trafficIncidents.length, byType };
  })() : null;
  const counts = {
    trainAlerts: trainAlerts?.alerts.length ?? 0,
    trainMessages: trainAlerts?.messages.length ?? 0,
    trainSignals: (trainAlerts?.alerts.length ?? 0) + (trainAlerts?.messages.length ?? 0),
    trafficSignals: trafficIncidents?.length ?? 0,
  };
  const coverage = getTransportCoverage(
    params.busStopCode,
    busArrivals as readonly Readonly<Record<string, unknown>>[] | null,
    nextArrival,
    trainAlerts as Readonly<{ alerts: readonly Readonly<Record<string, unknown>>[]; messages: readonly Readonly<Record<string, unknown>>[] }> | null,
    trafficIncidents as readonly Readonly<Record<string, unknown>>[] | null,
  );
  const opsLevel = getTransportOpsLevel(params, counts, nextArrival);
  const opsHeadline = buildTransportHeadline(opsLevel, focus, counts, primaryTrainLine, primaryIncidentType);
  const signals = buildTransportSignals(params, nextArrival, counts, primaryTrainLine, primaryIncidentType, coverage);
  const nextChecks = buildTransportNextChecks(params);

  const payload: BriefArtifact = {
    title: "Transport Brief",
    summary: [
      { label: "Network status", value: opsHeadline, source: "LTA" },
      { label: "Focus", value: focus, source: "LTA" },
      { label: "Next bus ETA", value: nextArrival, source: "LTA" },
      { label: "Train disruption count", value: counts.trainSignals, source: "LTA" },
      { label: "Traffic incident count", value: counts.trafficSignals, source: "LTA" },
    ],
    evidence: [
      { label: "Bus coverage", value: coverage.busCoverage, source: "LTA" },
      { label: "Bus services observed", value: busArrivals?.length ?? 0, source: "LTA" },
      { label: "Train alerts observed", value: counts.trainAlerts, source: "LTA" },
      { label: "Train messages observed", value: counts.trainMessages, source: "LTA" },
      { label: "Traffic incidents observed", value: counts.trafficSignals, source: "LTA" },
    ],
    records: {
      opsStatus: {
        level: opsLevel,
        headline: opsHeadline,
        focus,
        busCoverage: coverage.busCoverage,
        trainCoverage: coverage.trainCoverage,
        trafficCoverage: coverage.trafficCoverage,
      },
      signals,
      nextChecks,
      ...(stopSummary !== null ? { stopSummary } : {}),
      ...(incidentSummary !== null ? { incidentSummary } : {}),
      busArrivals: busArrivals ?? [],
      trainAlerts: trainAlerts?.alerts ?? [],
      trainAlertMessages: trainAlerts?.messages ?? [],
      trafficIncidents: trafficIncidents ?? [],
    },
    gaps,
    provenance: [
      toProvenance("LTA", "sg_lta_bus_arrivals", "Optional stop-level bus arrival timings for the supplied stop code and service.", true, busArrivals?.length ?? 0),
      toProvenance("LTA", "sg_lta_train_alerts", "Network-wide train service alert coverage and operator messages.", true, (trainAlerts?.alerts.length ?? 0) + (trainAlerts?.messages.length ?? 0)),
      toProvenance("LTA", "sg_lta_traffic_incidents", "Live road traffic incident coverage across Singapore.", true, trafficIncidents?.length ?? 0),
    ],
    freshness: [
      toFreshness("LTA bus arrivals", observedAt, nextArrival),
      toFreshness("LTA train alerts", observedAt, getFirstTimestamp(trainAlerts?.messages, ["createdDate"])),
      toFreshness("LTA traffic incidents", observedAt, null),
    ],
    limits: buildTransportLimits(params.busStopCode !== undefined),
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

const AREA_TO_REGION: Readonly<Record<string, string>> = {
  "Ang Mo Kio": "central", "Bedok": "east", "Bishan": "central", "Bukit Batok": "west",
  "Bukit Merah": "central", "Bukit Panjang": "west", "Bukit Timah": "central",
  "Choa Chu Kang": "west", "Clementi": "west", "Geylang": "central", "Hougang": "north",
  "Jurong East": "west", "Jurong West": "west", "Kallang": "central", "Marine Parade": "east",
  "Pasir Ris": "east", "Punggol": "north", "Queenstown": "central", "Sembawang": "north",
  "Sengkang": "north", "Serangoon": "central", "Tampines": "east", "Toa Payoh": "central",
  "Woodlands": "north", "Yishun": "north",
};

export const handleEnvironmentBrief = async (
  params: Readonly<{
    area?: string | undefined;
    region?: string | undefined;
    stationId?: string | undefined;
    date?: string | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];

  const [forecast, airQuality, rainfall] = await Promise.all([
    safeRead(
      "NEA_FORECAST_FAILED",
      "NEA forecast lookup failed",
      () => getForecast2Hr(params.area, params.date),
      gaps,
    ),
    safeRead(
      "NEA_AIR_QUALITY_FAILED",
      "NEA air-quality lookup failed",
      () => getAirQuality(params.region, params.date),
      gaps,
    ),
    safeRead(
      "NEA_RAINFALL_FAILED",
      "NEA rainfall lookup failed",
      () => getRainfall(params.stationId, params.date),
      gaps,
    ),
  ]);

  const primaryForecast = forecast?.[0];
  const primaryAirQuality = airQuality?.[0];
  const primaryRainfall = rainfall?.[0];
  const inferredRegion = params.region ?? (params.area !== undefined ? AREA_TO_REGION[params.area] ?? null : null);
  const focusArea = primaryForecast?.area ?? params.area ?? null;
  const focusRegion = primaryAirQuality?.region ?? inferredRegion ?? null;
  const focusStationId = primaryRainfall?.stationId ?? params.stationId ?? null;
  const focusStation = primaryRainfall?.stationName ?? focusStationId;
  const thresholds = {
    forecastRisk: getForecastRisk(primaryForecast?.forecast),
    airQualityBand: getAirQualityBand(primaryAirQuality?.psi24h),
    rainfallBand: getRainfallBand(primaryRainfall?.value),
  } as const;
  const opsLevel = getEnvironmentOpsLevel(thresholds);
  const opsHeadline = buildEnvironmentHeadline(opsLevel, focusArea, focusRegion, focusStation);
  const signals = buildEnvironmentSignals(
    primaryForecast as Readonly<Record<string, unknown>> | undefined,
    primaryAirQuality as Readonly<Record<string, unknown>> | undefined,
    primaryRainfall as Readonly<Record<string, unknown>> | undefined,
    thresholds,
  );
  const outdoorConditions = (() => {
    if (opsLevel === "caution") {
      const reasons: string[] = [];
      if (thresholds.forecastRisk === "caution") reasons.push("thunderstorms or heavy rain expected");
      if (thresholds.airQualityBand === "caution") reasons.push("poor air quality (PSI > 100)");
      if (thresholds.rainfallBand === "caution") reasons.push("heavy rainfall detected");
      return { advisory: "Avoid prolonged outdoor activities", reasons };
    }
    if (opsLevel === "watch") {
      const reasons: string[] = [];
      if (thresholds.forecastRisk === "watch") reasons.push("rain or showers possible");
      if (thresholds.airQualityBand === "watch") reasons.push("moderate air quality (PSI 51-100)");
      if (thresholds.rainfallBand === "watch") reasons.push("light rainfall detected");
      return { advisory: "Carry umbrella, monitor conditions", reasons };
    }
    if (opsLevel === "clear") return { advisory: "Safe for outdoor activities", reasons: [] };
    return { advisory: "Conditions unknown, check individual signals", reasons: [] };
  })();
  const nextChecks = buildEnvironmentNextChecks(params, {
    focusArea,
    focusRegion,
    stationId: focusStationId,
  });

  const payload: BriefArtifact = {
    title: "Environment Brief",
    summary: [
      { label: "Monitoring status", value: opsHeadline, source: "NEA" },
      { label: "Forecast risk", value: thresholds.forecastRisk, source: "NEA" },
      { label: "PSI band", value: thresholds.airQualityBand, source: "NEA" },
      { label: "PSI 24h", value: primaryAirQuality?.psi24h ?? null, source: "NEA" },
      { label: "Rainfall band", value: thresholds.rainfallBand, source: "NEA" },
      { label: "Rainfall", value: primaryRainfall?.value ?? null, source: "NEA" },
      { label: "Focus area", value: focusArea, source: "NEA" },
      { label: "Focus region", value: focusRegion, source: "NEA" },
      { label: "Focus station", value: focusStation, source: "NEA" },
    ],
    evidence: [
      { label: "Forecast rows", value: forecast?.length ?? 0, source: "NEA" },
      { label: "Air-quality rows", value: airQuality?.length ?? 0, source: "NEA" },
      { label: "Rainfall rows", value: rainfall?.length ?? 0, source: "NEA" },
      { label: "Forecast input", value: primaryForecast?.forecast ?? null, source: "NEA" },
      { label: "PSI input", value: primaryAirQuality?.psi24h ?? null, source: "NEA" },
      { label: "Rainfall input", value: primaryRainfall?.value ?? null, source: "NEA" },
    ],
    records: {
      opsStatus: {
        level: opsLevel,
        headline: opsHeadline,
        focusArea,
        focusRegion,
        focusStation,
      },
      outdoorConditions,
      thresholds,
      signals,
      nextChecks,
      rainfallStation: primaryRainfall !== undefined ? {
        stationId: primaryRainfall.stationId ?? null,
        stationName: primaryRainfall.stationName ?? null,
      } : null,
      forecast: forecast ?? [],
      airQuality: airQuality ?? [],
      rainfall: rainfall ?? [],
    },
    gaps,
    provenance: [
      toProvenance("NEA", "sg_nea_forecast_2hr", "2-hour forecast coverage for the requested area or the first available forecast area.", false, forecast?.length ?? 0),
      toProvenance("NEA", "sg_nea_air_quality", "Regional air-quality coverage for the requested region or the first available regional reading.", false, airQuality?.length ?? 0),
      toProvenance("NEA", "sg_nea_rainfall", "Station rainfall coverage for the requested station or the first available station reading.", false, rainfall?.length ?? 0),
    ],
    freshness: [
      toFreshness("NEA forecast", observedAt, getFirstTimestamp(forecast, ["updatedAt", "validFrom"])),
      toFreshness("NEA air quality", observedAt, getFirstTimestamp(airQuality, ["updatedAt"])),
      toFreshness("NEA rainfall", observedAt, getFirstTimestamp(rainfall, ["timestamp"])),
    ],
    limits: buildEnvironmentLimits(params.area !== undefined, params.region !== undefined, params.stationId !== undefined),
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

export const briefToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_business_dossier",
    description: "Build a cross-registry business dossier across ACRA, BCA, and CEA using explicit company, UEN, or estate-agent identifiers.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct business-diligence tools.",
    inputSchema: BusinessDossierBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleBusinessDossier(validateInput(BusinessDossierSchema, input)),
  },
  {
    name: "sg_property_brief",
    description: "Build a location and property brief for one Singapore planning area, postal code, or address across OneMap, URA, HDB, and optional live context.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct property, map, and environment tools.",
    inputSchema: PropertyBriefBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handlePropertyBrief(validateInput(PropertyBriefSchema, input)),
  },
  {
    name: "sg_macro_brief",
    description: "Build a compact Singapore macro starter brief using MAS market data and SingStat dataset entrypoints.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct MAS and SingStat tools.",
    inputSchema: MacroBriefSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleMacroBrief(validateInput(MacroBriefSchema, input)),
  },
  {
    name: "sg_transport_brief",
    description: "Build a live transport operations brief over LTA bus arrivals, train alerts, and traffic incidents.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct LTA operational tools.",
    inputSchema: TransportBriefInputSchema,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransportBrief(validateInput(TransportBriefSchema, input)),
  },
  {
    name: "sg_environment_brief",
    description: "Build a live environment brief over NEA forecast, air-quality, and rainfall signals.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct NEA monitoring tools.",
    inputSchema: EnvironmentBriefInputSchema,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleEnvironmentBrief(validateInput(EnvironmentBriefSchema, input)),
  },
];
