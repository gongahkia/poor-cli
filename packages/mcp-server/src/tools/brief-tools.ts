import { createHash, randomUUID } from "node:crypto";
import {
  BriefArtifactSchema,
  BusinessDossierBaseSchema,
  BusinessDossierSchema,
  createLogger,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@dude/shared";
import type {
  BriefArtifact,
  BriefFreshnessItem,
  BriefLimit,
  BriefProvenanceItem,
  EvidenceGap,
  NextCheck,
  RiskFlag,
  ToolResult,
} from "@dude/shared";
import { MasDataset } from "@dude/shared";
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
import { getTableData as getSingStatTableData } from "../apis/singstat/client.js";
import { normalizeTransactions } from "../apis/ura/normalizer.js";
import { getPropertyTransactions } from "../apis/ura/client.js";
import { getEcdaChildcareCentres } from "../apis/ecda/client.js";
import { getHawkerCentres } from "../apis/hawker/client.js";
import { getMsfFamilyServices, getMsfStudentCareServices, getMsfSocialServiceOffices } from "../apis/msf/client.js";
import { getPaCommunityOutlets, getPaResidentNetworkCentres } from "../apis/pa/client.js";
import { getSportSgFacilities } from "../apis/sportsg/client.js";
import { buildBusinessDossierArtifact } from "../diligence/business-dossier.js";
import { fetchNormalizedMasRecords } from "./mas-tools.js";
import { buildMapPayloadFromPoints, withMapUiMetadata } from "./map-payload.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import { lookupPlanningArea } from "./ura-tools.js";

const MAP_TOOL_META = withMapUiMetadata(undefined);
const logger = createLogger("brief-tools");

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
  options?: {
    readonly structuredContent?: Readonly<Record<string, unknown>>;
    readonly _meta?: Readonly<Record<string, unknown>>;
  },
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
      ...(options?.structuredContent ?? {}),
    },
    ...(options?._meta === undefined ? {} : { _meta: options._meta }),
  };
};

const toGap = (code: string, message: string): EvidenceGap => ({ code, message });
const toLimit = (code: string, message: string): BriefLimit => ({ code, message });

const buildContextIds = (
  includeContextIds: boolean | undefined,
): Readonly<Record<string, unknown>> | undefined => {
  if (includeContextIds !== true) {
    return undefined;
  }
  const requestId = randomUUID();
  return {
    traceId: requestId,
    requestId,
  };
};

const safeRead = async <T>(
  code: string,
  message: string,
  read: () => Promise<T>,
  gaps: EvidenceGap[],
  context?: Readonly<Record<string, unknown>>,
): Promise<T | null> => {
  try {
    return await read();
  } catch (error) {
    const renderedError = error instanceof Error ? error.message : String(error);
    logger.warn("brief source read failed", {
      gapCode: code,
      sourceMessage: message,
      error,
      ...(context ?? {}),
    });
    gaps.push(toGap(code, `${message}: ${renderedError}`));
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

const toSignalId = (namespace: string, parts: readonly (string | number | null | undefined)[]): string => {
  const key = parts.map((part) => String(part ?? "")).join("|");
  const digest = createHash("sha1").update(`${namespace}|${key}`).digest("hex").slice(0, 12);
  return `${namespace}:${digest}`;
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
      signalId: toSignalId("transport-bus", [params.busStopCode, params.serviceNo ?? "all"]),
      signalClass: "bus_eta",
      source: "bus",
      level: nextArrival === null ? "unknown" : "normal",
      headline: nextArrival === null
        ? `No current bus ETA available for ${focus}.`
        : `Next bus ETA for ${focus} is ${nextArrival}.`,
      focus,
      busStopCode: params.busStopCode,
      ...(params.serviceNo === undefined ? {} : { serviceNo: params.serviceNo }),
      nextArrival,
      coverage: coverage.busCoverage,
    });
  }

  signals.push({
    signalId: toSignalId("transport-train", [primaryTrainLine ?? "network"]),
    signalClass: "train_alert",
    source: "train",
    level: counts.trainAlerts + counts.trainMessages > 0 ? "disrupted" : coverage.trainCoverage === "unavailable" ? "unknown" : "normal",
    headline:
      counts.trainAlerts + counts.trainMessages > 0
        ? primaryTrainLine === null
          ? `${counts.trainAlerts} train alert(s) and ${counts.trainMessages} message(s) reported.`
          : `${counts.trainAlerts} train alert(s) and ${counts.trainMessages} message(s) reported on ${primaryTrainLine}.`
        : "No active train alerts reported.",
    alertCount: counts.trainAlerts,
    messageCount: counts.trainMessages,
    primaryLine: primaryTrainLine,
    coverage: coverage.trainCoverage,
  });

  signals.push({
    signalId: toSignalId("transport-traffic", [primaryIncidentType ?? "all"]),
    signalClass: "traffic_incident",
    source: "traffic",
    level: counts.trafficSignals > 0 ? "advisory" : coverage.trafficCoverage === "unavailable" ? "unknown" : "normal",
    headline:
      counts.trafficSignals > 0
        ? primaryIncidentType === null
          ? `${counts.trafficSignals} traffic incident(s) reported.`
          : `${counts.trafficSignals} traffic incident(s) reported, including ${primaryIncidentType}.`
        : "No active traffic incidents reported.",
    incidentCount: counts.trafficSignals,
    primaryIncidentType,
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
    const forecastAreaKey = typeof primaryForecast["area"] === "string" ? primaryForecast["area"] : "unknown";
    const forecastTextKey = typeof primaryForecast["forecast"] === "string" ? primaryForecast["forecast"] : "unknown";
    signals.push({
      signalId: toSignalId("environment-forecast", [forecastAreaKey, forecastTextKey]),
      signalClass: "forecast",
      source: "forecast",
      level: thresholds.forecastRisk,
      headline: `Forecast ${String(primaryForecast["forecast"] ?? "")} for ${String(primaryForecast["area"] ?? "the requested area")}.`,
      area: primaryForecast["area"] ?? null,
      forecast: primaryForecast["forecast"] ?? null,
      updatedAt: primaryForecast["updatedAt"] ?? null,
      validFrom: primaryForecast["validFrom"] ?? null,
      validTo: primaryForecast["validTo"] ?? null,
    });
  }

  if (primaryAirQuality !== undefined) {
    const airRegionKey = typeof primaryAirQuality["region"] === "string" ? primaryAirQuality["region"] : "unknown";
    signals.push({
      signalId: toSignalId("environment-air-quality", [airRegionKey]),
      signalClass: "air_quality",
      source: "air_quality",
      level: thresholds.airQualityBand,
      headline: `PSI 24h is ${String(primaryAirQuality["psi24h"] ?? "unknown")} for ${String(primaryAirQuality["region"] ?? "the requested region")}.`,
      region: primaryAirQuality["region"] ?? null,
      psi24h: primaryAirQuality["psi24h"] ?? null,
      pm25OneHourly: primaryAirQuality["pm25OneHourly"] ?? null,
      updatedAt: primaryAirQuality["updatedAt"] ?? null,
    });
  }

  if (primaryRainfall !== undefined) {
    const rainfallStationKey = typeof primaryRainfall["stationId"] === "string"
      ? primaryRainfall["stationId"]
      : typeof primaryRainfall["stationName"] === "string"
        ? primaryRainfall["stationName"]
        : "unknown";
    signals.push({
      signalId: toSignalId("environment-rainfall", [rainfallStationKey]),
      signalClass: "rainfall",
      source: "rainfall",
      level: thresholds.rainfallBand,
      headline: `Rainfall is ${String(primaryRainfall["value"] ?? "unknown")} ${String(primaryRainfall["unit"] ?? "")}`.trim()
        + ` at ${String(primaryRainfall["stationName"] ?? primaryRainfall["stationId"] ?? "the requested station")}.`,
      stationId: primaryRainfall["stationId"] ?? null,
      stationName: primaryRainfall["stationName"] ?? null,
      value: primaryRainfall["value"] ?? null,
      unit: primaryRainfall["unit"] ?? null,
      timestamp: primaryRainfall["timestamp"] ?? null,
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

const getTransportPrimaryDriver = (
  level: "disrupted" | "advisory" | "unknown" | "normal",
  nextArrival: string | null,
  primaryTrainLine: string | null,
  primaryIncidentType: string | null,
): string | null => {
  if (level === "disrupted") {
    return primaryTrainLine === null ? "train alerts active" : `train alerts on ${primaryTrainLine}`;
  }
  if (level === "advisory") {
    return primaryIncidentType === null ? "traffic incidents active" : primaryIncidentType;
  }
  if (nextArrival !== null) {
    return `next arrival ${nextArrival}`;
  }
  if (level === "unknown") {
    return "no current bus ETA available";
  }
  return "no active disruption signals";
};

const getTransportEscalationTier = (
  level: "disrupted" | "advisory" | "unknown" | "normal",
): "tier0_monitor" | "tier1_notify" | "tier2_investigate" => {
  if (level === "disrupted") return "tier2_investigate";
  if (level === "advisory" || level === "unknown") return "tier1_notify";
  return "tier0_monitor";
};

const buildTrainByLine = (
  alerts: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, number>> => {
  const counts: Record<string, number> = {};
  for (const alert of alerts) {
    const line = typeof alert["line"] === "string" && alert["line"].trim() !== ""
      ? alert["line"]
      : "Unknown";
    counts[line] = (counts[line] ?? 0) + 1;
  }
  return counts;
};

const buildTrafficByType = (
  incidents: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, number>> => {
  const counts: Record<string, number> = {};
  for (const incident of incidents) {
    const type = typeof incident["type"] === "string" && incident["type"].trim() !== ""
      ? incident["type"]
      : "Unknown";
    counts[type] = (counts[type] ?? 0) + 1;
  }
  return counts;
};

const buildStopDetail = (
  params: Readonly<{ busStopCode?: string | undefined; serviceNo?: string | undefined }>,
  nextArrival: string | null,
  busArrivals: readonly Readonly<Record<string, unknown>>[] | null,
): Readonly<Record<string, unknown>> | null => {
  if (params.busStopCode === undefined || busArrivals === null) {
    return null;
  }

  const waitMins: number[] = [];
  const arrivals = busArrivals.map((service) => {
    const serviceArrivals = Array.isArray(service["arrivals"])
      ? service["arrivals"] as readonly Readonly<Record<string, unknown>>[]
      : [];
    const eta = typeof serviceArrivals[0]?.["estimatedArrival"] === "string"
      ? serviceArrivals[0]!["estimatedArrival"]
      : null;
    if (eta !== null) {
      const diff = (new Date(eta).getTime() - Date.now()) / 60000;
      if (Number.isFinite(diff) && diff >= 0) {
        waitMins.push(Math.round(diff * 10) / 10);
      }
    }

    return {
      serviceNo: service["serviceNo"] ?? null,
      operator: service["operator"] ?? null,
      nextArrival: eta,
      arrivalCount: serviceArrivals.length,
      arrivals: serviceArrivals,
    };
  });

  return {
    busStopCode: params.busStopCode,
    ...(params.serviceNo === undefined ? {} : { serviceNo: params.serviceNo }),
    serviceCount: busArrivals.length,
    nextArrival,
    avgWaitMinutes: waitMins.length > 0
      ? Math.round((waitMins.reduce((sum, value) => sum + value, 0) / waitMins.length) * 10) / 10
      : null,
    arrivals,
  };
};

const getEnvironmentPrimaryDriver = (
  level: "caution" | "watch" | "clear" | "unknown",
  thresholds: Readonly<{
    forecastRisk: "caution" | "watch" | "clear" | "unknown";
    airQualityBand: "caution" | "watch" | "clear" | "unknown";
    rainfallBand: "caution" | "watch" | "clear" | "unknown";
  }>,
): string | null => {
  if (thresholds.forecastRisk === level && level !== "clear" && level !== "unknown") {
    return "forecast";
  }
  if (thresholds.airQualityBand === level && level !== "clear" && level !== "unknown") {
    return "air quality";
  }
  if (thresholds.rainfallBand === level && level !== "clear" && level !== "unknown") {
    return "rainfall";
  }
  if (level === "clear") {
    return "no adverse forecast, air-quality, or rainfall signals";
  }
  if (level === "unknown") {
    return "signals unavailable";
  }
  return null;
};

const getEnvironmentEscalationTier = (
  level: "caution" | "watch" | "clear" | "unknown",
): "tier0_monitor" | "tier1_notify" | "tier2_investigate" => {
  if (level === "caution") return "tier2_investigate";
  if (level === "watch" || level === "unknown") return "tier1_notify";
  return "tier0_monitor";
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

const medianSorted = (values: readonly number[]): number | null => {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? Math.round(((sorted[mid - 1]! + sorted[mid]!) / 2) * 100) / 100 : sorted[mid]!;
};

const quantileSorted = (sorted: readonly number[], q: number): number | null => {
  if (sorted.length === 0) return null;
  if (sorted.length === 1) return sorted[0] ?? null;
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  const lower = sorted[base];
  const upper = sorted[base + 1];
  if (lower === undefined) return null;
  if (upper === undefined) return lower;
  return Math.round((lower + rest * (upper - lower)) * 100) / 100;
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
  const sorted = [...prices].sort((a, b) => a - b);
  return {
    count: prices.length,
    median: medianSorted(prices),
    p25: quantileSorted(sorted, 0.25),
    p75: quantileSorted(sorted, 0.75),
    min: sorted[0] ?? null,
    max: sorted[sorted.length - 1] ?? null,
    average: Math.round((prices.reduce((s, v) => s + v, 0) / prices.length) * 100) / 100,
    latestMonth: dates[dates.length - 1] ?? null,
  };
};

const buildPropertyDealChecklist = (
  uraRollup: Readonly<Record<string, unknown>> | null,
  hdbRollup: Readonly<Record<string, unknown>> | null,
  planningArea: string | null,
  propertyType: string | undefined,
  includeEnvironment: boolean,
  includeTransport: boolean,
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
  if (!includeEnvironment) {
    flags.push({ code: "NO_ENVIRONMENT_CONTEXT", severity: "low", message: "Environment context (NEA forecast and air quality) was not included. Enable includeEnvironment for livability signals.", source: "brief-input" });
  }
  if (!includeTransport) {
    flags.push({ code: "NO_TRANSPORT_CONTEXT", severity: "low", message: "Transport context (LTA train and traffic signals) was not included. Enable includeTransport for connectivity signals.", source: "brief-input" });
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
    checks.push({ tool: "sg_ura_property_transactions", reason: "Retrieve detailed URA transactions for deeper price analysis.", input: { propertyType: "residential", area: planningArea } });
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
  return null; // fail loud rather than surface an unnamed field as a headline metric
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

const computeSingStatDelta = (
  series: readonly Readonly<Record<string, unknown>>[],
): number | null => {
  if (series.length < 2) return null;
  const latest = Number(series[0]?.["value"]);
  const prev = Number(series[1]?.["value"]);
  if (!Number.isFinite(latest) || !Number.isFinite(prev) || prev === 0) return null;
  return Math.round(((latest - prev) / Math.abs(prev)) * 10000) / 100;
};

const SINGSTAT_PERIOD_MONTHS: Readonly<Record<string, number>> = {
  Jan: 1,
  Feb: 2,
  Mar: 3,
  Apr: 4,
  May: 5,
  Jun: 6,
  Jul: 7,
  Aug: 8,
  Sep: 9,
  Oct: 10,
  Nov: 11,
  Dec: 12,
};

const MACRO_SINGSTAT_TABLES = {
  gdp: {
    tableId: "M015631",
    label: "GDP growth rate",
    preferredVariables: ["GDP At Current Market Prices"],
  },
  cpiYoY: {
    tableId: "M213781",
    label: "CPI YoY",
    preferredVariables: ["All Items"],
  },
  cpiIndex: {
    tableId: "M213751",
    label: "CPI index",
    preferredVariables: ["All Items"],
  },
} as const;

const getSingStatPeriodSortKey = (period: string): number => {
  const quarterMatch = period.match(/^(\d{4})\s+(\d)Q$/i);
  if (quarterMatch !== null) {
    return Number(quarterMatch[1]) * 100 + Number(quarterMatch[2]) * 3;
  }

  const monthMatch = period.match(/^(\d{4})\s+([A-Za-z]{3})$/);
  if (monthMatch !== null) {
    return Number(monthMatch[1]) * 100 + (SINGSTAT_PERIOD_MONTHS[monthMatch[2] ?? ""] ?? 0);
  }

  const yearMatch = period.match(/^(\d{4})$/);
  if (yearMatch !== null) {
    return Number(yearMatch[1]) * 100;
  }

  return Number.NEGATIVE_INFINITY;
};

const selectSingStatRows = (
  rows: readonly Readonly<Record<string, unknown>>[],
  preferredVariables: readonly string[],
): readonly Readonly<Record<string, unknown>>[] => {
  const normalizedTargets = preferredVariables.map((value) => value.trim().toLowerCase());
  return rows
    .filter((row) => {
      const variable = typeof row["variable"] === "string" ? row["variable"].trim().toLowerCase() : "";
      return normalizedTargets.includes(variable);
    })
    .sort((left, right) => getSingStatPeriodSortKey(String(right["period"] ?? "")) - getSingStatPeriodSortKey(String(left["period"] ?? "")));
};

const getLatestSingStatMetric = (
  rows: readonly Readonly<Record<string, unknown>>[],
  preferredVariables: readonly string[],
): Readonly<Record<string, unknown>> | null => {
  return selectSingStatRows(rows, preferredVariables)[0] ?? null;
};

const sliceLatestSingStatMetrics = (
  rows: readonly Readonly<Record<string, unknown>>[],
  preferredVariables: readonly string[],
  limit = 8,
): readonly Readonly<Record<string, unknown>>[] => {
  return selectSingStatRows(rows, preferredVariables).slice(0, limit);
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
  checks.push({ tool: "sg_singstat_timeseries", reason: "Retrieve a bounded GDP time series for trend analysis.", input: { tableId: MACRO_SINGSTAT_TABLES.gdp.tableId, indicator: "GDP At Current Market Prices", startYear: 2020, endYear: new Date().getFullYear() } });
  checks.push({ tool: "sg_singstat_search", reason: "Discover additional SingStat datasets for deeper macro analysis.", input: { keyword: "Singapore unemployment" } });
  return checks;
};

const buildMacroLimits = (): readonly BriefLimit[] => [
  toLimit("STARTER_SNAPSHOT", "This brief is a compact macro starter, not a full economic research note or narrative analysis."),
  toLimit("BOUNDED_SINGSTAT_SERIES", "SingStat coverage is limited to validated GDP and CPI tables with compact recent slices, not open-ended macro table coverage."),
  toLimit("NO_FORWARD_VIEW", "The brief reports current or requested historical values and does not forecast or interpret future macro conditions."),
];

const formatMacroHeadlineValue = (
  value: string | number | null | undefined,
  suffix = "",
): string | null => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return `${value}${suffix}`;
  }
  if (typeof value === "string" && value.trim() !== "") {
    return `${value}${suffix}`;
  }
  return null;
};

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
    modules?: readonly ("acra" | "bca" | "cea" | "gebiz" | "boa" | "hsa" | "hlb")[] | undefined;
    sectorHints?: readonly ("construction" | "real_estate" | "architecture" | "healthcare" | "hospitality" | "procurement")[] | undefined;
    includeExternalDiligence?: boolean | undefined;
    includeContextIds?: boolean | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const payload = await buildBusinessDossierArtifact(params);
  const contextIds = buildContextIds(params.includeContextIds);
  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown", {
    ...(contextIds === undefined ? {} : { structuredContent: { contextIds } }),
  });
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
    includeContextIds?: boolean | undefined;
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

  const uraTransactionsRaw = planningArea === null
    ? null
    : await safeRead(
        "URA_TRANSACTIONS_FAILED",
        "URA transaction lookup failed",
        () => getPropertyTransactions(params.propertyType ?? "residential", planningArea, undefined),
        gaps,
      );
  const uraTransactions = uraTransactionsRaw === null
    ? null
    : normalizeTransactions(uraTransactionsRaw);

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
  const uraMedian = uraRollup?.["median"] as number | null ?? null;
  const hdbMedian = hdbRollup?.["median"] as number | null ?? null;
  const marketComparison = privateAverage !== null && resaleAverage !== null
    ? {
        privateAvg: privateAverage,
        hdbResaleAvg: resaleAverage,
        delta: Math.round((privateAverage - resaleAverage) * 100) / 100,
        ratio: Math.round((privateAverage / resaleAverage) * 100) / 100,
        privateMedian: uraMedian,
        hdbResaleMedian: hdbMedian,
        medianDelta: uraMedian !== null && hdbMedian !== null
          ? Math.round((uraMedian - hdbMedian) * 100) / 100
          : null,
        medianRatio: uraMedian !== null && hdbMedian !== null && hdbMedian !== 0
          ? Math.round((uraMedian / hdbMedian) * 100) / 100
          : null,
        privateCount: (uraRollup?.["count"] as number | null) ?? null,
        hdbResaleCount: (hdbRollup?.["count"] as number | null) ?? null,
      }
    : null;
  const dealChecklist = buildPropertyDealChecklist(uraRollup, hdbRollup, planningArea, params.propertyType, includeEnvironment, includeTransport);
  const geospatialConfidence = (() => {
    if (planningArea !== null && firstGeocode !== null) {
      return {
        level: "high",
        reason: "Location resolved from both geocode and planning-area lookup.",
      };
    }
    if (planningArea !== null && params.planningArea !== undefined) {
      return {
        level: "medium",
        reason: "Planning area was supplied directly without geocode confirmation.",
      };
    }
    if (planningArea !== null) {
      return {
        level: "medium",
        reason: "Planning area resolved, but geocode signal is partial.",
      };
    }
    return {
      level: "low",
      reason: "Planning area could not be resolved from the supplied location input.",
    };
  })();
  const environmentSignals = includeEnvironment
    ? {
        forecastRisk: getForecastRisk(primaryForecast?.forecast),
        airQualityBand: getAirQualityBand(primaryAirQuality?.psi24h),
        tier: (() => {
          const levels = [
            getForecastRisk(primaryForecast?.forecast),
            getAirQualityBand(primaryAirQuality?.psi24h),
          ];
          if (levels.includes("caution")) return "caution";
          if (levels.includes("watch")) return "watch";
          if (levels.includes("clear")) return "clear";
          return "unknown";
        })(),
      }
    : null;
  const transportSignals = includeTransport
    ? {
        trainAlertCount: trainAlerts?.alerts.length ?? 0,
        trainMessageCount: trainAlerts?.messages.length ?? 0,
        trafficIncidentCount: trafficIncidents?.length ?? 0,
        tier: (trainAlerts?.alerts.length ?? 0) + (trainAlerts?.messages.length ?? 0) > 0
          ? "disrupted"
          : (trafficIncidents?.length ?? 0) > 0
            ? "advisory"
            : trainAlerts === null || trafficIncidents === null
              ? "unknown"
              : "clear",
      }
    : null;
  const divergenceWarnings: readonly RiskFlag[] = marketComparison === null
    ? []
      : marketComparison.ratio >= 1.8
      ? [{
          code: "MARKET_CONTEXT_DIVERGENCE",
          severity: "medium" as const,
          message: `Private vs HDB average ratio is ${marketComparison.ratio}, which exceeds the high-divergence threshold of 1.8.`,
          source: "URA/HDB",
        }]
      : marketComparison.ratio <= 0.55
        ? [{
            code: "MARKET_CONTEXT_DIVERGENCE",
            severity: "medium" as const,
            message: `Private vs HDB average ratio is ${marketComparison.ratio}, which is below the low-divergence threshold of 0.55.`,
            source: "URA/HDB",
          }]
        : [];
  const propertyRiskFlags: readonly RiskFlag[] = [
    ...dealChecklist,
    ...divergenceWarnings,
    ...(geospatialConfidence.level === "low"
      ? [{
          code: "LOW_GEOSPATIAL_CONFIDENCE",
          severity: "high" as const,
          message: "Location resolution confidence is low; verify planning-area context before making decisions.",
          source: "OneMap/URA",
        }]
      : []),
  ];
  const propertyNextChecks = buildPropertyNextChecks(planningArea, firstGeocode?.postal ?? params.postalCode ?? null, firstGeocode?.lat ?? null, firstGeocode?.lng ?? null);
  const locationResolution = {
    requestedPlanningArea: params.planningArea ?? null,
    requestedPostalCode: params.postalCode ?? null,
    requestedAddress: params.address ?? null,
    resolvedPlanningArea: planningArea,
    resolvedRegion: region,
    resolvedPostalCode: firstGeocode?.postal ?? params.postalCode ?? null,
    lat: firstGeocode?.lat ?? null,
    lng: firstGeocode?.lng ?? null,
  };
  const toFreshnessStatus = (upstreamTimestamp: string | null): "fresh" | "stale" | "unknown" => {
    if (upstreamTimestamp === null) {
      return "unknown";
    }
    const parsed = Date.parse(upstreamTimestamp);
    if (!Number.isFinite(parsed)) {
      return "unknown";
    }
    const ageHours = (Date.now() - parsed) / (1000 * 60 * 60);
    return ageHours > 24 * 90 ? "stale" : "fresh";
  };
  const provenanceSummary = [
    { source: "OneMap", role: "location_resolution", status: firstGeocode === null ? "missing" : "available" },
    { source: "URA", role: "planning_and_transactions", status: uraTransactions === null ? "missing" : "available" },
    { source: "HDB", role: "resale_context", status: hdbResale === null ? "missing" : "available" },
    ...(includeEnvironment
      ? [
          { source: "NEA", role: "forecast_context", status: forecast === null ? "missing" : "available" },
          { source: "NEA", role: "air_quality_context", status: airQuality === null ? "missing" : "available" },
        ]
      : []),
    ...(includeTransport
      ? [
          { source: "LTA", role: "train_alert_context", status: trainAlerts === null ? "missing" : "available" },
          { source: "LTA", role: "traffic_incident_context", status: trafficIncidents === null ? "missing" : "available" },
        ]
      : []),
  ];
  const freshnessSummary = [
    { source: "URA transactions", upstreamTimestamp: getFirstTimestamp(uraTransactions, ["contractDate", "date"]), status: toFreshnessStatus(getFirstTimestamp(uraTransactions, ["contractDate", "date"])) },
    { source: "HDB resale", upstreamTimestamp: getFirstTimestamp(hdbResale, ["month"]), status: toFreshnessStatus(getFirstTimestamp(hdbResale, ["month"])) },
    ...(includeEnvironment
      ? [
          { source: "NEA forecast", upstreamTimestamp: getFirstTimestamp(forecast, ["updatedAt", "validFrom"]), status: toFreshnessStatus(getFirstTimestamp(forecast, ["updatedAt", "validFrom"])) },
          { source: "NEA air quality", upstreamTimestamp: getFirstTimestamp(airQuality, ["updatedAt"]), status: toFreshnessStatus(getFirstTimestamp(airQuality, ["updatedAt"])) },
        ]
      : []),
  ];

  const payload: BriefArtifact = {
    title: "Property Brief",
    summary: [
      { label: "Resolved planning area", value: planningArea, source: "URA" },
      { label: "Region", value: region, source: "URA" },
      { label: "Resolved postal code", value: firstGeocode?.postal ?? params.postalCode ?? null, source: "OneMap" },
      { label: "Address confidence", value: geospatialConfidence.level, source: "OneMap/URA" },
      { label: "Address confidence reason", value: geospatialConfidence.reason, source: "OneMap/URA" },
      { label: "Resolution path", value: planningArea !== null && firstGeocode !== null ? "geocode + planning_area" : params.planningArea !== undefined && planningArea !== null ? "planning_area_direct" : planningArea !== null ? "planning_area_only" : "unresolved", source: "OneMap/URA" },
      { label: "Private transaction count", value: (uraRollup?.["count"] as number | null) ?? 0, source: "URA" },
      { label: "Private transaction average", value: privateAverage, source: "URA" },
      { label: "Private transaction median", value: uraRollup?.["median"] as number | null ?? null, source: "URA" },
      { label: "Private transaction range", value: uraRollup === null ? null : `${uraRollup["min"]} - ${uraRollup["max"]}`, source: "URA" },
      { label: "Private transaction latest month", value: (uraRollup?.["latestMonth"] as string | null) ?? null, source: "URA" },
      { label: "HDB resale count", value: (hdbRollup?.["count"] as number | null) ?? 0, source: "HDB" },
      { label: "HDB resale average", value: resaleAverage, source: "HDB" },
      { label: "HDB resale median", value: hdbRollup?.["median"] as number | null ?? null, source: "HDB" },
      { label: "HDB resale range", value: hdbRollup === null ? null : `${hdbRollup["min"]} - ${hdbRollup["max"]}`, source: "HDB" },
      { label: "HDB resale latest month", value: (hdbRollup?.["latestMonth"] as string | null) ?? null, source: "HDB" },
      { label: "Private vs HDB average delta", value: marketComparison?.delta ?? null, source: "URA/HDB" },
      { label: "Private vs HDB average ratio", value: marketComparison?.ratio ?? null, source: "URA/HDB" },
      { label: "Private vs HDB median delta", value: marketComparison?.medianDelta ?? null, source: "URA/HDB" },
      { label: "Private vs HDB median ratio", value: marketComparison?.medianRatio ?? null, source: "URA/HDB" },
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
      locationResolution,
      confidence: {
        geospatial: geospatialConfidence,
      },
      geocode: firstGeocode === null ? [] : [firstGeocode],
      planningArea: planningRecords ?? [],
      uraTransactions: uraTransactions ?? [],
      uraRollup: uraRollup ?? {},
      hdbResale: hdbResale ?? [],
      hdbRollup: hdbRollup ?? {},
      marketComparison: marketComparison ?? {},
      contextSignals: {
        transport: transportSignals,
        environment: environmentSignals,
      },
      dealChecklist: {
        items: dealChecklist.map((item) => ({ code: item.code, severity: item.severity, message: item.message, source: item.source })),
        outstandingCount: dealChecklist.length,
        highSeverityCount: dealChecklist.filter((item) => item.severity === "high").length,
      },
      provenanceSummary,
      freshnessSummary,
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
    riskFlags: propertyRiskFlags,
    nextChecks: propertyNextChecks,
  };

  const mapPayload = firstGeocode === null
    ? null
    : buildMapPayloadFromPoints("sg_property_brief", [{
      lat: firstGeocode.lat,
      lng: firstGeocode.lng,
      label: firstGeocode.building || firstGeocode.address || firstGeocode.postal || planningArea || "Resolved location",
      description: firstGeocode.address,
    }]);
  const contextIds = buildContextIds(params.includeContextIds);

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown", {
    ...(mapPayload === null && contextIds === undefined
      ? {}
      : {
          structuredContent: {
            ...(mapPayload === null ? {} : { mapPayload }),
            ...(contextIds === undefined ? {} : { contextIds }),
          },
        }),
    ...(mapPayload === null ? {} : { _meta: MAP_TOOL_META }),
  });
};

export const handleMacroBrief = async (
  params: Readonly<{
    currency?: string | undefined;
    date?: string | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
    includeContextIds?: boolean | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  const currency = (params.currency ?? "USD").toUpperCase();

  const [exchangeRates, interestRates, financialStats, gdpTable, cpiYoYTable, cpiIndexTable] = await Promise.all([
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
      "SingStat GDP table lookup failed",
      () => getSingStatTableData(MACRO_SINGSTAT_TABLES.gdp.tableId),
      gaps,
    ),
    safeRead(
      "SINGSTAT_CPI_YOY_FAILED",
      "SingStat CPI inflation table lookup failed",
      () => getSingStatTableData(MACRO_SINGSTAT_TABLES.cpiYoY.tableId),
      gaps,
    ),
    safeRead(
      "SINGSTAT_CPI_INDEX_FAILED",
      "SingStat CPI index table lookup failed",
      () => getSingStatTableData(MACRO_SINGSTAT_TABLES.cpiIndex.tableId),
      gaps,
    ),
  ]);

  const latestExchange = exchangeRates?.[0];
  const latestInterest = interestRates?.[0];
  const latestBanking = financialStats?.[0];
  const exchangeKey = `${currency.toLowerCase()}_sgd`;
  const exchangeValue = latestExchange?.[exchangeKey]
    ?? latestExchange?.[`${currency.toLowerCase()}_sgd_100`]
    ?? null;
  const exchangeHeadlineValue = typeof exchangeValue === "number" || typeof exchangeValue === "string"
    ? exchangeValue
    : null;
  const soraMetric = extractNamedMasMetric(latestInterest, ["sora", "sora_1m", "sora_3m", "sora_6m", "sor_average"]);
  const bankingMetric = extractNamedMasMetric(latestBanking, ["total_deposits", "total_loans", "total_assets", "dbd_deposit"]);
  if (latestInterest !== undefined && soraMetric === null) {
    gaps.push(toGap("MAS_SORA_METRIC_UNMAPPED", "MAS interest-rate record did not expose a known SORA field. No SORA headline metric is returned."));
  }
  if (latestBanking !== undefined && bankingMetric === null) {
    gaps.push(toGap("MAS_BANKING_METRIC_UNMAPPED", "MAS banking record did not expose a known deposits/loans/assets field. No banking headline metric is returned."));
  }
  const fxDelta = computeMasDelta(exchangeRates, exchangeKey);
  const soraDelta = soraMetric !== null ? computeMasDelta(interestRates, soraMetric.key) : null;
  const bankingDelta = bankingMetric !== null ? computeMasDelta(financialStats, bankingMetric.key) : null;
  const gdpTableId = gdpTable?.metadata.title === undefined ? null : MACRO_SINGSTAT_TABLES.gdp.tableId;
  const cpiTableId = cpiYoYTable?.metadata.title === undefined ? null : MACRO_SINGSTAT_TABLES.cpiYoY.tableId;
  const cpiIndexTableId = cpiIndexTable?.metadata.title === undefined ? null : MACRO_SINGSTAT_TABLES.cpiIndex.tableId;
  const latestGdp = gdpTable === null ? null : getLatestSingStatMetric(gdpTable.rows as readonly Readonly<Record<string, unknown>>[], MACRO_SINGSTAT_TABLES.gdp.preferredVariables);
  const latestCpiYoY = cpiYoYTable === null ? null : getLatestSingStatMetric(cpiYoYTable.rows as readonly Readonly<Record<string, unknown>>[], MACRO_SINGSTAT_TABLES.cpiYoY.preferredVariables);
  const latestCpiIndex = cpiIndexTable === null ? null : getLatestSingStatMetric(cpiIndexTable.rows as readonly Readonly<Record<string, unknown>>[], MACRO_SINGSTAT_TABLES.cpiIndex.preferredVariables);
  const gdpSeries = gdpTable === null ? [] : sliceLatestSingStatMetrics(gdpTable.rows as readonly Readonly<Record<string, unknown>>[], MACRO_SINGSTAT_TABLES.gdp.preferredVariables);
  const cpiYoYSeries = cpiYoYTable === null ? [] : sliceLatestSingStatMetrics(cpiYoYTable.rows as readonly Readonly<Record<string, unknown>>[], MACRO_SINGSTAT_TABLES.cpiYoY.preferredVariables);
  const cpiIndexSeries = cpiIndexTable === null ? [] : sliceLatestSingStatMetrics(cpiIndexTable.rows as readonly Readonly<Record<string, unknown>>[], MACRO_SINGSTAT_TABLES.cpiIndex.preferredVariables);
  const gdpDelta = computeSingStatDelta(gdpSeries);
  const cpiYoYDelta = computeSingStatDelta(cpiYoYSeries);
  const cpiIndexDelta = computeSingStatDelta(cpiIndexSeries);
  const macroNextChecks = buildMacroNextChecks(gdpTableId, cpiTableId);
  const trackedKpis = {
    currency,
    fx: {
      metric: `${currency}/SGD`,
      value: typeof exchangeValue === "number" ? exchangeValue : exchangeValue as string | null,
      date: typeof latestExchange?.["date"] === "string" ? latestExchange["date"] : null,
      deltaPercent: fxDelta,
    },
    interestRate: {
      metric: soraMetric === null ? "SORA" : formatMetricLabel(soraMetric.key),
      key: soraMetric?.key ?? null,
      value: soraMetric?.value ?? null,
      deltaPercent: soraDelta,
    },
    banking: {
      metric: bankingMetric === null ? "MAS Banking (unavailable)" : formatMetricLabel(bankingMetric.key),
      key: bankingMetric?.key ?? null,
      value: bankingMetric?.value ?? null,
      deltaPercent: bankingDelta,
    },
    singstatSeries: {
      gdpTableId,
      gdpPeriod: typeof latestGdp?.["period"] === "string" ? latestGdp["period"] : null,
      gdpValue: typeof latestGdp?.["value"] === "number" ? latestGdp["value"] : latestGdp?.["value"] ?? null,
      gdpDeltaPercent: gdpDelta,
      cpiYoYTableId: cpiTableId,
      cpiYoYPeriod: typeof latestCpiYoY?.["period"] === "string" ? latestCpiYoY["period"] : null,
      cpiYoYValue: typeof latestCpiYoY?.["value"] === "number" ? latestCpiYoY["value"] : latestCpiYoY?.["value"] ?? null,
      cpiYoYDeltaPercent: cpiYoYDelta,
      cpiIndexTableId,
      cpiIndexPeriod: typeof latestCpiIndex?.["period"] === "string" ? latestCpiIndex["period"] : null,
      cpiIndexValue: typeof latestCpiIndex?.["value"] === "number" ? latestCpiIndex["value"] : latestCpiIndex?.["value"] ?? null,
      cpiIndexDeltaPercent: cpiIndexDelta,
    },
  };
  const macroHeadlines = [
    {
      code: "FX",
      headline: `${currency}/SGD${formatMacroHeadlineValue(exchangeHeadlineValue) === null ? " unavailable" : ` at ${formatMacroHeadlineValue(exchangeHeadlineValue)}`}`,
      source: "MAS",
      date: typeof latestExchange?.["date"] === "string" ? latestExchange["date"] : null,
    },
    {
      code: "SORA",
      headline: `${soraMetric === null ? "SORA" : formatMetricLabel(soraMetric.key)}${formatMacroHeadlineValue(soraMetric?.value, "%") === null ? " unavailable" : ` at ${formatMacroHeadlineValue(soraMetric?.value, "%")}`}`,
      source: "MAS",
      date: typeof latestInterest?.["date"] === "string" ? latestInterest["date"] : null,
    },
    {
      code: "BANKING",
      headline: `${bankingMetric === null ? "MAS banking metric" : formatMetricLabel(bankingMetric.key)}${formatMacroHeadlineValue(bankingMetric?.value) === null ? " unavailable" : ` at ${formatMacroHeadlineValue(bankingMetric?.value)}`}`,
      source: "MAS",
      date: typeof latestBanking?.["date"] === "string" ? latestBanking["date"] : null,
    },
    {
      code: "GDP",
      headline: `GDP at current prices${formatMacroHeadlineValue(latestGdp?.["value"] as string | number | null | undefined) === null ? " unavailable" : ` at ${formatMacroHeadlineValue(latestGdp?.["value"] as string | number | null | undefined)} for ${String(latestGdp?.["period"] ?? "unknown period")}`}`,
      source: "SingStat",
      tableId: gdpTableId,
    },
    {
      code: "CPI_YOY",
      headline: `CPI YoY${formatMacroHeadlineValue(latestCpiYoY?.["value"] as string | number | null | undefined, "%") === null ? " unavailable" : ` at ${formatMacroHeadlineValue(latestCpiYoY?.["value"] as string | number | null | undefined, "%")} for ${String(latestCpiYoY?.["period"] ?? "unknown period")}`}`,
      source: "SingStat",
      tableId: cpiTableId,
    },
  ];

  const payload: BriefArtifact = {
    title: "Macro Brief",
    summary: [
      { label: `${currency}/SGD`, value: typeof exchangeValue === "number" ? exchangeValue : exchangeValue as string | null, source: "MAS" },
      { label: "FX date", value: typeof latestExchange?.["date"] === "string" ? latestExchange["date"] : null, source: "MAS" },
      { label: "FX period delta %", value: fxDelta, source: "MAS" },
      { label: soraMetric === null ? "SORA" : formatMetricLabel(soraMetric.key), value: soraMetric?.value ?? null, source: "MAS" },
      { label: "SORA period delta %", value: soraDelta, source: "MAS" },
      { label: bankingMetric === null ? "MAS Banking (unavailable)" : formatMetricLabel(bankingMetric.key), value: bankingMetric?.value ?? null, source: "MAS" },
      { label: "Banking period delta %", value: bankingDelta, source: "MAS" },
      { label: "GDP period", value: typeof latestGdp?.["period"] === "string" ? latestGdp["period"] : null, source: "SingStat" },
      { label: "GDP at current prices", value: typeof latestGdp?.["value"] === "number" || typeof latestGdp?.["value"] === "string" ? latestGdp["value"] : null, source: "SingStat" },
      { label: "GDP period delta %", value: gdpDelta, source: "SingStat" },
      { label: "GDP table ID", value: gdpTableId, source: "SingStat" },
      { label: "CPI YoY period", value: typeof latestCpiYoY?.["period"] === "string" ? latestCpiYoY["period"] : null, source: "SingStat" },
      { label: "CPI YoY %", value: typeof latestCpiYoY?.["value"] === "number" || typeof latestCpiYoY?.["value"] === "string" ? latestCpiYoY["value"] : null, source: "SingStat" },
      { label: "CPI YoY period delta %", value: cpiYoYDelta, source: "SingStat" },
      { label: "CPI YoY table ID", value: cpiTableId, source: "SingStat" },
      { label: "CPI index", value: typeof latestCpiIndex?.["value"] === "number" || typeof latestCpiIndex?.["value"] === "string" ? latestCpiIndex["value"] : null, source: "SingStat" },
      { label: "CPI index period delta %", value: cpiIndexDelta, source: "SingStat" },
      { label: "CPI index table ID", value: cpiIndexTableId, source: "SingStat" },
    ],
    evidence: [
      { label: "FX rows", value: exchangeRates?.length ?? 0, source: "MAS" },
      { label: "SORA rows", value: interestRates?.length ?? 0, source: "MAS" },
      { label: "Banking rows", value: financialStats?.length ?? 0, source: "MAS" },
      { label: "GDP rows", value: gdpSeries.length, source: "SingStat" },
      { label: "CPI YoY rows", value: cpiYoYSeries.length, source: "SingStat" },
      { label: "CPI index rows", value: cpiIndexSeries.length, source: "SingStat" },
      { label: "Primary SORA key", value: soraMetric?.key ?? null, source: "MAS" },
      { label: "Primary banking key", value: bankingMetric?.key ?? null, source: "MAS" },
    ],
    records: {
      kpis: trackedKpis,
      exchangeRates: exchangeRates ?? [],
      interestRates: interestRates ?? [],
      financialStats: financialStats ?? [],
      gdpSeries,
      cpiYoYSeries,
      cpiIndexSeries,
      headlines: macroHeadlines,
    },
    gaps,
    provenance: [
      toProvenance("MAS", "sg_mas_exchange_rates", "Exchange-rate coverage for the requested currency and date range.", false, exchangeRates?.length ?? 0),
      toProvenance("MAS", "sg_mas_interest_rates", "SORA interest-rate coverage for the requested date range.", false, interestRates?.length ?? 0),
      toProvenance("MAS", "sg_mas_financial_stats", "Banking-statistics coverage for the requested date range.", false, financialStats?.length ?? 0),
      toProvenance("SingStat", "sg_singstat_table", "Validated GDP and CPI table reads for current macro series.", false, gdpSeries.length + cpiYoYSeries.length + cpiIndexSeries.length),
    ],
    freshness: [
      toFreshness("MAS exchange rates", observedAt, getFirstTimestamp(exchangeRates, ["date"])),
      toFreshness("MAS interest rates", observedAt, getFirstTimestamp(interestRates, ["date"])),
      toFreshness("MAS banking stats", observedAt, getFirstTimestamp(financialStats, ["date"])),
      toFreshness("SingStat GDP table", observedAt, gdpTable?.metadata.lastUpdated ?? null),
      toFreshness("SingStat CPI YoY table", observedAt, cpiYoYTable?.metadata.lastUpdated ?? null),
      toFreshness("SingStat CPI index table", observedAt, cpiIndexTable?.metadata.lastUpdated ?? null),
    ],
    limits: buildMacroLimits(),
    nextChecks: macroNextChecks,
  };

  const contextIds = buildContextIds(params.includeContextIds);
  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown", {
    ...(contextIds === undefined ? {} : { structuredContent: { contextIds } }),
  });
};

export const handleTransportBrief = async (
  params: Readonly<{
    busStopCode?: string | undefined;
    serviceNo?: string | undefined;
    includeContextIds?: boolean | undefined;
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
  const followups = buildTransportNextChecks(params);
  const stop = buildStopDetail(
    params,
    nextArrival,
    busArrivals as readonly Readonly<Record<string, unknown>>[] | null,
  );
  const primaryDriver = getTransportPrimaryDriver(opsLevel, nextArrival, primaryTrainLine, primaryIncidentType);
  const escalationTier = getTransportEscalationTier(opsLevel);
  const statusSignalId = toSignalId("transport-status", [focus, opsLevel, primaryTrainLine, primaryIncidentType]);
  const actionTemplates = [
    {
      signalClass: "train_alert",
      tier: escalationTier,
      action: counts.trainSignals > 0
        ? "Escalate to transport-ops channel and monitor new train-alert updates every 5 minutes."
        : "Keep passive monitoring on train alerts.",
    },
    {
      signalClass: "traffic_incident",
      tier: escalationTier,
      action: counts.trafficSignals > 0
        ? "Notify field-ops or logistics owners about active traffic incidents."
        : "No traffic escalation required.",
    },
    {
      signalClass: "bus_eta",
      tier: escalationTier,
      action: params.busStopCode !== undefined
        ? nextArrival === null
          ? "Re-run stop-level ETA checks and verify stop code or service number."
          : "Use current ETA as the expected passenger-facing arrival signal."
        : "No stop-specific bus ETA requested.",
    },
  ] as const;
  const trainByLine = buildTrainByLine(
    trainAlerts?.alerts as unknown as readonly Readonly<Record<string, unknown>>[] ?? [],
  );
  const trafficByType = buildTrafficByType(
    trafficIncidents as unknown as readonly Readonly<Record<string, unknown>>[] ?? [],
  );

  const payload: BriefArtifact = {
    title: "Transport Brief",
    summary: [
      { label: "Transport status", value: opsLevel, source: "LTA" },
      { label: "Focus", value: focus, source: "LTA" },
      { label: "Primary driver", value: primaryDriver, source: "LTA" },
    ],
    evidence: [
      { label: "Bus services observed", value: busArrivals?.length ?? 0, source: "LTA" },
      { label: "Train alerts observed", value: counts.trainAlerts, source: "LTA" },
      { label: "Train messages observed", value: counts.trainMessages, source: "LTA" },
      { label: "Traffic incidents observed", value: counts.trafficSignals, source: "LTA" },
    ],
    records: {
      status: {
        signalId: statusSignalId,
        level: opsLevel,
        escalationTier,
        headline: opsHeadline,
        focus,
      },
      coverage: {
        bus: {
          status: coverage.busCoverage,
          requestedBusStopCode: params.busStopCode ?? null,
          requestedServiceNo: params.serviceNo ?? null,
          servicesObserved: busArrivals?.length ?? 0,
        },
        train: {
          status: coverage.trainCoverage,
          alertCount: counts.trainAlerts,
          messageCount: counts.trainMessages,
        },
        traffic: {
          status: coverage.trafficCoverage,
          incidentCount: counts.trafficSignals,
        },
      },
      serviceStatusByMode: {
        bus: {
          status: params.busStopCode === undefined
            ? "not_requested"
            : busArrivals === null
              ? "unavailable"
              : (busArrivals.length === 0 ? "empty" : "healthy"),
          nextArrival,
        },
        train: {
          status: trainAlerts === null
            ? "unavailable"
            : counts.trainAlerts > 0
              ? "alerts_active"
              : counts.trainMessages > 0
                ? "messages_only"
                : "healthy",
          alertCount: counts.trainAlerts,
          messageCount: counts.trainMessages,
        },
        traffic: {
          status: trafficIncidents === null
            ? "unavailable"
            : counts.trafficSignals > 0
              ? "incidents_active"
              : "healthy",
          incidentCount: counts.trafficSignals,
        },
      },
      signals,
      network: {
        trainAlertCount: counts.trainAlerts,
        trainMessageCount: counts.trainMessages,
        trainByLine,
        trafficIncidentCount: counts.trafficSignals,
        trafficByType,
      },
      ...(stop === null ? {} : { stop }),
      followups,
      actionTemplates,
      signalIds: {
        status: statusSignalId,
        signals: signals.map((signal) => signal["signalId"] ?? null).filter((value): value is string => typeof value === "string"),
      },
      raw: {
        busArrivals: busArrivals ?? [],
        trainAlerts: trainAlerts?.alerts ?? [],
        trainMessages: trainAlerts?.messages ?? [],
        trafficIncidents: trafficIncidents ?? [],
      },
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
    nextChecks: followups as readonly NextCheck[],
    riskFlags: buildTransportRiskFlags(opsLevel, counts, coverage, params.busStopCode !== undefined),
  };

  const contextIds = buildContextIds(params.includeContextIds);
  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown", {
    ...(contextIds === undefined ? {} : { structuredContent: { contextIds } }),
  });
};

const buildTransportRiskFlags = (
  opsLevel: string,
  counts: Readonly<{ trainAlerts: number; trainMessages: number; trafficSignals: number }>,
  coverage: Readonly<{ busCoverage: string; trainCoverage: string; trafficCoverage: string }>,
  busStopRequested: boolean,
): readonly RiskFlag[] => {
  const flags: RiskFlag[] = [];
  if (counts.trainAlerts > 0) {
    flags.push({
      code: "TRAIN_ALERTS_ACTIVE",
      severity: counts.trainAlerts > 1 ? "high" : "medium",
      message: `${counts.trainAlerts} active train alert(s); escalate to transport-ops channel.`,
      source: "LTA",
    });
  }
  if (counts.trafficSignals > 0) {
    flags.push({
      code: "TRAFFIC_INCIDENTS_ACTIVE",
      severity: counts.trafficSignals > 5 ? "medium" : "low",
      message: `${counts.trafficSignals} active traffic incident(s) on the network.`,
      source: "LTA",
    });
  }
  if (busStopRequested && coverage.busCoverage === "unavailable") {
    flags.push({
      code: "BUS_COVERAGE_UNAVAILABLE",
      severity: "medium",
      message: "Stop-level bus coverage was requested but is unavailable; verify stop code and service number.",
      source: "LTA",
    });
  }
  if (opsLevel === "disrupted") {
    flags.push({
      code: "OPS_LEVEL_DISRUPTED",
      severity: "high",
      message: "Aggregated transport ops level is disrupted; one or more modes are returning warning signals.",
      source: "aggregated",
    });
  }
  return flags;
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
    includeContextIds?: boolean | undefined;
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
  const pm25 = typeof primaryAirQuality?.pm25TwentyFourHourly === "number"
    ? primaryAirQuality.pm25TwentyFourHourly
    : (typeof primaryAirQuality?.pm25OneHourly === "number" ? primaryAirQuality.pm25OneHourly : null);
  const booleanFlags = {
    rainActive: thresholds.rainfallBand === "watch" || thresholds.rainfallBand === "caution",
    rainHeavy: thresholds.rainfallBand === "caution",
    forecastThundery: thresholds.forecastRisk === "caution",
    psiUnhealthy: thresholds.airQualityBand === "caution",
    pm25Unhealthy: pm25 !== null && pm25 > 55,
  } as const;
  const fallbackChain = [
    { level: "area", requested: params.area ?? null, resolved: primaryForecast?.area ?? params.area ?? null, source: "NEA forecast" },
    { level: "region", requested: params.region ?? null, resolved: primaryAirQuality?.region ?? inferredRegion ?? null, source: params.region === undefined && inferredRegion !== null ? "AREA_TO_REGION inferred" : "NEA air-quality direct" },
    { level: "station", requested: params.stationId ?? null, resolved: primaryRainfall?.stationId ?? params.stationId ?? null, source: "NEA rainfall" },
  ];
  const opsLevel = getEnvironmentOpsLevel(thresholds);
  const opsHeadline = buildEnvironmentHeadline(opsLevel, focusArea, focusRegion, focusStation);
  const signals = buildEnvironmentSignals(
    primaryForecast as Readonly<Record<string, unknown>> | undefined,
    primaryAirQuality as Readonly<Record<string, unknown>> | undefined,
    primaryRainfall as Readonly<Record<string, unknown>> | undefined,
    thresholds,
  );
  const thresholdAdvisory = (() => {
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
  const followups = buildEnvironmentNextChecks(params, {
    focusArea,
    focusRegion,
    stationId: focusStationId,
  });
  const primaryDriver = getEnvironmentPrimaryDriver(opsLevel, thresholds);
  const escalationTier = getEnvironmentEscalationTier(opsLevel);
  const statusSignalId = toSignalId("environment-status", [focusArea, focusRegion, focusStationId, opsLevel]);
  const actionTemplates = [
    {
      signalClass: "forecast",
      tier: escalationTier,
      action: thresholds.forecastRisk === "caution"
        ? "Escalate weather caution to operations leads and defer exposed outdoor plans."
        : thresholds.forecastRisk === "watch"
          ? "Track forecast refresh and keep fallback plan ready."
          : "No forecast-triggered escalation required.",
    },
    {
      signalClass: "air_quality",
      tier: escalationTier,
      action: thresholds.airQualityBand === "caution"
        ? "Issue poor-air advisory for sensitive groups and extended outdoor exposure."
        : thresholds.airQualityBand === "watch"
          ? "Advise moderate-air-quality precautions for prolonged activities."
          : "No air-quality escalation required.",
    },
    {
      signalClass: "rainfall",
      tier: escalationTier,
      action: thresholds.rainfallBand === "caution"
        ? "Pause rainfall-sensitive operations and monitor station updates closely."
        : thresholds.rainfallBand === "watch"
          ? "Prepare rainfall contingency while monitoring short-interval updates."
          : "No rainfall escalation required.",
    },
  ] as const;
  const forecastCoverage = forecast === null
    ? "unavailable"
    : primaryForecast === undefined
      ? "missing"
      : "available";
  const airQualityCoverage = airQuality === null
    ? "unavailable"
    : primaryAirQuality === undefined
      ? "missing"
      : "available";
  const rainfallCoverage = rainfall === null
    ? "unavailable"
    : primaryRainfall === undefined
      ? "missing"
      : "available";

  const payload: BriefArtifact = {
    title: "Environment Brief",
    summary: [
      { label: "Monitoring status", value: opsLevel, source: "NEA" },
      { label: "Focus", value: buildEnvironmentScopeLabel(focusArea, focusRegion, focusStation), source: "NEA" },
      { label: "Primary driver", value: primaryDriver, source: "NEA" },
    ],
    evidence: [
      { label: "Forecast rows", value: forecast?.length ?? 0, source: "NEA" },
      { label: "Air-quality rows", value: airQuality?.length ?? 0, source: "NEA" },
      { label: "Rainfall rows", value: rainfall?.length ?? 0, source: "NEA" },
    ],
    records: {
      status: {
        signalId: statusSignalId,
        level: opsLevel,
        escalationTier,
        headline: opsHeadline,
      },
      coverage: {
        forecast: {
          status: forecastCoverage,
          requestedArea: params.area ?? null,
          resolvedArea: focusArea,
          rowCount: forecast?.length ?? 0,
        },
        airQuality: {
          status: airQualityCoverage,
          requestedRegion: params.region ?? null,
          resolvedRegion: focusRegion,
          rowCount: airQuality?.length ?? 0,
        },
        rainfall: {
          status: rainfallCoverage,
          requestedStationId: params.stationId ?? null,
          resolvedStationId: focusStationId,
          resolvedStationName: focusStation,
          rowCount: rainfall?.length ?? 0,
        },
      },
      signals,
      thresholds: {
        ...thresholds,
        advisory: thresholdAdvisory.advisory,
        reasons: thresholdAdvisory.reasons,
      },
      flags: booleanFlags,
      fallbackChain,
      focus: {
        area: focusArea,
        region: focusRegion,
        stationId: focusStationId,
        stationName: focusStation,
      },
      followups,
      actionTemplates,
      signalIds: {
        status: statusSignalId,
        signals: signals.map((signal) => signal["signalId"] ?? null).filter((value): value is string => typeof value === "string"),
      },
      raw: {
        forecastRows: forecast ?? [],
        airQualityRows: airQuality ?? [],
        rainfallRows: rainfall ?? [],
      },
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
    nextChecks: followups as readonly NextCheck[],
    riskFlags: buildEnvironmentRiskFlags(thresholds, booleanFlags, opsLevel),
  };

  const contextIds = buildContextIds(params.includeContextIds);
  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown", {
    ...(contextIds === undefined ? {} : { structuredContent: { contextIds } }),
  });
};

const buildEnvironmentRiskFlags = (
  thresholds: Readonly<{ forecastRisk: string; airQualityBand: string; rainfallBand: string }>,
  flags: Readonly<{ rainActive: boolean; rainHeavy: boolean; forecastThundery: boolean; psiUnhealthy: boolean; pm25Unhealthy: boolean }>,
  opsLevel: string,
): readonly RiskFlag[] => {
  const list: RiskFlag[] = [];
  if (thresholds.forecastRisk === "caution") {
    list.push({
      code: "FORECAST_THUNDERY",
      severity: "high",
      message: "Forecast indicates thundery or stormy conditions; outdoor activity should be deferred.",
      source: "NEA",
    });
  }
  if (thresholds.airQualityBand === "caution" || flags.psiUnhealthy) {
    list.push({
      code: "AIR_QUALITY_UNHEALTHY",
      severity: "high",
      message: "PSI 24h reading is in the unhealthy band (>100); avoid prolonged outdoor exertion.",
      source: "NEA",
    });
  } else if (thresholds.airQualityBand === "watch") {
    list.push({
      code: "AIR_QUALITY_WATCH",
      severity: "medium",
      message: "PSI 24h reading is in the moderate band (51-100); sensitive groups should reduce prolonged exertion.",
      source: "NEA",
    });
  }
  if (flags.pm25Unhealthy) {
    list.push({
      code: "PM25_UNHEALTHY",
      severity: "medium",
      message: "PM2.5 reading exceeds the 55 ug/m3 short-term advisory threshold.",
      source: "NEA",
    });
  }
  if (thresholds.rainfallBand === "caution" || flags.rainHeavy) {
    list.push({
      code: "RAIN_HEAVY",
      severity: "medium",
      message: "Heavy rainfall reported at the focus station; expect localised flooding risk.",
      source: "NEA",
    });
  }
  if (opsLevel === "caution") {
    list.push({
      code: "OPS_LEVEL_CAUTION",
      severity: "high",
      message: "Aggregated environment ops level is caution; outdoor operations should be paused.",
      source: "aggregated",
    });
  }
  return list;
};

type CivicModule = "pa" | "sportsg" | "ecda" | "msf" | "hawker";
type CivicSourceResult = { category: string; module: CivicModule; count: number; records: readonly Record<string, unknown>[] };

export const handleCivicBrief = async (
  params: Readonly<{
    postalCode?: string | undefined;
    address?: string | undefined;
    lat?: number | undefined;
    lng?: number | undefined;
    radiusKm?: number | undefined;
    modules?: readonly CivicModule[] | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  let lat = params.lat;
  let lng = params.lng;
  const searchVal = params.postalCode ?? params.address;
  if (lat === undefined && lng === undefined && searchVal !== undefined) {
    const geo = await safeRead("GEOCODE_FAILED", "OneMap geocode failed", () => geocode(searchVal, 1), gaps);
    const first = geo?.[0];
    if (first !== undefined) {
      lat = first.lat;
      lng = first.lng;
    }
  }
  if (lat === undefined || lng === undefined) {
    gaps.push(toGap("NO_LOCATION", "No resolvable location provided. Supply postalCode, address, or lat/lng."));
  }
  const coordParams = { lat, lng, radiusKm: params.radiusKm ?? 3, limit: 10 };
  const enabled: ReadonlySet<CivicModule> = new Set(params.modules ?? ["pa", "sportsg", "ecda", "msf", "hawker"]);
  const optionalRead = async <T>(active: boolean, code: string, message: string, read: () => Promise<T>): Promise<T | null> => {
    if (!active) return null;
    return safeRead(code, message, read, gaps);
  };
  const [pa, paRn, sport, ecda, msfFamily, msfStudent, msfSso, hawker] = await Promise.all([
    optionalRead(enabled.has("pa"), "PA_OUTLETS_FAILED", "PA community outlets lookup failed", () => getPaCommunityOutlets(coordParams)),
    optionalRead(enabled.has("pa"), "PA_RESIDENT_FAILED", "PA resident network centres lookup failed", () => getPaResidentNetworkCentres(coordParams)),
    optionalRead(enabled.has("sportsg"), "SPORTSG_FAILED", "SportSG facilities lookup failed", () => getSportSgFacilities(coordParams)),
    optionalRead(enabled.has("ecda"), "ECDA_FAILED", "ECDA childcare centres lookup failed", () => getEcdaChildcareCentres(coordParams)),
    optionalRead(enabled.has("msf"), "MSF_FAMILY_FAILED", "MSF family services lookup failed", () => getMsfFamilyServices(coordParams)),
    optionalRead(enabled.has("msf"), "MSF_STUDENT_FAILED", "MSF student care services lookup failed", () => getMsfStudentCareServices(coordParams)),
    optionalRead(enabled.has("msf"), "MSF_SSO_FAILED", "MSF social service offices lookup failed", () => getMsfSocialServiceOffices(coordParams)),
    optionalRead(enabled.has("hawker"), "HAWKER_FAILED", "Hawker centres lookup failed", () => getHawkerCentres({ ...coordParams })),
  ]);
  const allSources: CivicSourceResult[] = [
    { category: "Community Clubs", module: "pa", count: pa?.length ?? 0, records: (pa ?? []) as unknown as Record<string, unknown>[] },
    { category: "Resident Network Centres", module: "pa", count: paRn?.length ?? 0, records: (paRn ?? []) as unknown as Record<string, unknown>[] },
    { category: "Sports Facilities", module: "sportsg", count: sport?.length ?? 0, records: (sport ?? []) as unknown as Record<string, unknown>[] },
    { category: "Childcare Centres", module: "ecda", count: ecda?.length ?? 0, records: (ecda ?? []) as unknown as Record<string, unknown>[] },
    { category: "Family Services", module: "msf", count: msfFamily?.length ?? 0, records: (msfFamily ?? []) as unknown as Record<string, unknown>[] },
    { category: "Student Care", module: "msf", count: msfStudent?.length ?? 0, records: (msfStudent ?? []) as unknown as Record<string, unknown>[] },
    { category: "Social Service Offices", module: "msf", count: msfSso?.length ?? 0, records: (msfSso ?? []) as unknown as Record<string, unknown>[] },
    { category: "Hawker Centres", module: "hawker", count: hawker?.length ?? 0, records: (hawker ?? []) as unknown as Record<string, unknown>[] },
  ];
  const sources = allSources.filter((source) => enabled.has(source.module));
  const totalFacilities = sources.reduce((sum, s) => sum + s.count, 0);
  const locationLabel = params.postalCode ?? params.address ?? (lat !== undefined ? `${lat}, ${lng}` : "unknown");
  const records: Record<string, unknown> = {};
  for (const s of sources) records[s.category] = s.records;
  const payload: BriefArtifact = {
    title: "Civic Brief",
    summary: [
      { label: "Location", value: locationLabel, source: "OneMap" },
      { label: "Search radius", value: `${coordParams.radiusKm} km`, source: "input" },
      { label: "Total facilities found", value: totalFacilities, source: "aggregated" },
      ...sources.filter((s) => s.count > 0).map((s) => ({ label: s.category, value: s.count, source: s.category })),
    ],
    evidence: sources.map((s) => ({ label: s.category, value: s.count, source: s.category })),
    records,
    gaps,
    provenance: [
      ...(enabled.has("pa") ? [toProvenance("PA", "sg_pa_community_outlets", "Community clubs and PAssion WaVe outlets within the search radius.", false, pa?.length ?? 0)] : []),
      ...(enabled.has("pa") ? [toProvenance("PA", "sg_pa_resident_network_centres", "Residents' committee and network centres within the search radius.", false, paRn?.length ?? 0)] : []),
      ...(enabled.has("sportsg") ? [toProvenance("SportSG", "sg_sportsg_facilities", "Sport facilities within the search radius.", false, sport?.length ?? 0)] : []),
      ...(enabled.has("ecda") ? [toProvenance("ECDA", "sg_ecda_childcare_centres", "Childcare centres within the search radius.", false, ecda?.length ?? 0)] : []),
      ...(enabled.has("msf") ? [toProvenance("MSF", "sg_msf_family_services", "Family service centres within the search radius.", false, msfFamily?.length ?? 0)] : []),
      ...(enabled.has("msf") ? [toProvenance("MSF", "sg_msf_student_care_services", "Student care services within the search radius.", false, msfStudent?.length ?? 0)] : []),
      ...(enabled.has("msf") ? [toProvenance("MSF", "sg_msf_social_service_offices", "Social service offices within the search radius.", false, msfSso?.length ?? 0)] : []),
      ...(enabled.has("hawker") ? [toProvenance("Hawker", "sg_hawker_centres", "Hawker centres within the search radius.", false, hawker?.length ?? 0)] : []),
    ],
    freshness: [toFreshness("Civic directories", observedAt, null)],
    limits: [
      toLimit("RADIUS_BOUND", `Results bounded to ${coordParams.radiusKm} km radius from the search location.`),
      toLimit("PER_CATEGORY_CAP", "Each category returns at most 10 nearest facilities."),
      toLimit("NO_OPERATING_HOURS", "Operating hours and real-time availability are not included."),
    ],
    nextChecks: buildCivicNextChecks(coordParams, totalFacilities, lat, lng),
    riskFlags: buildCivicRiskFlags(totalFacilities, lat, lng, coordParams.radiusKm),
  };
  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

const buildCivicNextChecks = (
  coordParams: Readonly<{ radiusKm: number }>,
  totalFacilities: number,
  lat: number | undefined,
  lng: number | undefined,
): readonly NextCheck[] => {
  const checks: NextCheck[] = [];
  if (lat === undefined || lng === undefined) {
    checks.push({
      tool: "sg_onemap_geocode",
      reason: "Resolve a postal code, address, or building name into coordinates before re-running the civic brief.",
      input: {},
    });
    return checks;
  }
  if (totalFacilities === 0 && coordParams.radiusKm < 5) {
    checks.push({
      tool: "sg_civic_brief",
      reason: "Widen the search radius when no facilities surface at the current radius.",
      input: { lat, lng, radiusKm: Math.min(coordParams.radiusKm * 2, 10) },
    });
  }
  checks.push({
    tool: "sg_pa_community_outlets",
    reason: "Drill into community-club inventory directly when civic-brief categories are too aggregated.",
    input: { lat, lng, radiusKm: coordParams.radiusKm, limit: 10 },
  });
  checks.push({
    tool: "sg_ecda_childcare_centres",
    reason: "Drill into childcare directory directly for family-relocation workflows.",
    input: { lat, lng, radiusKm: coordParams.radiusKm, limit: 10 },
  });
  return checks;
};

const buildCivicRiskFlags = (
  totalFacilities: number,
  lat: number | undefined,
  lng: number | undefined,
  radiusKm: number,
): readonly RiskFlag[] => {
  const flags: RiskFlag[] = [];
  if (lat === undefined || lng === undefined) {
    flags.push({
      code: "LOCATION_UNRESOLVED",
      severity: "high",
      message: "Could not resolve location to coordinates; civic results are empty until geocode succeeds.",
      source: "OneMap",
    });
    return flags;
  }
  if (totalFacilities === 0) {
    flags.push({
      code: "NO_FACILITIES_IN_RADIUS",
      severity: "medium",
      message: `No civic facilities found within ${radiusKm} km of the requested location; widen radius or verify the location.`,
      source: "aggregated",
    });
  }
  return flags;
};

export const briefToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_business_dossier",
    description: "Build a cross-registry business dossier across ACRA, BCA, CEA, and explicit BOA, HSA, HLB, or GeBIZ modules using company, UEN, or estate-agent identifiers.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct business-diligence tools.",
    inputSchema: BusinessDossierBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleBusinessDossier(validateInput(BusinessDossierSchema, input)),
  },
];
