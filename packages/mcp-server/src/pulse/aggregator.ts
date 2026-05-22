import {
  evaluatePulseFreshness,
  resolvePulseSourceHealthStatus,
} from "@swee-sg/shared";
import type {
  EvidenceGap,
  PulseSignal,
  PulseSnapshot,
  PulseSourceHealth,
} from "@swee-sg/shared";
import {
  getRoadOpenings,
  getRoadWorks,
  getTrafficImages,
  getTrafficIncidents,
  getTrainAlerts,
} from "../apis/lta/client.js";
import { getAirQuality, getForecast2Hr, getRainfall } from "../apis/nea/client.js";

export type PulseSnapshotInput = {
  readonly area?: string;
  readonly region?: string;
  readonly stationId?: string;
  readonly focus?: "mobility" | "weather" | "all";
};

const nowIso = (): string => new Date().toISOString();
const DEFAULT_MAX_AGE_SECONDS = 15 * 60;

const makeId = (...parts: readonly unknown[]): string =>
  parts.map((part) => String(part ?? "na").toLowerCase().replace(/[^a-z0-9]+/g, "-")).join(":");

const toGap = (code: string, message: string): EvidenceGap => ({ code, message });

const withSourceHealth = (params: {
  readonly source: string;
  readonly sourceTool: string;
  readonly observedAt: string;
  readonly upstreamTimestamp: string | null;
  readonly recordCount: number;
  readonly gaps?: readonly EvidenceGap[];
}): PulseSourceHealth => {
  const freshness = evaluatePulseFreshness({
    observedAt: params.observedAt,
    upstreamTimestamp: params.upstreamTimestamp,
    maxAgeSeconds: DEFAULT_MAX_AGE_SECONDS,
  });
  const health = {
    source: params.source,
    sourceTool: params.sourceTool,
    status: "ready",
    observedAt: params.observedAt,
    recordCount: params.recordCount,
    freshness,
    gaps: params.gaps ?? [],
    provenance: [{
      source: params.source,
      sourceTool: params.sourceTool,
      observedAt: params.observedAt,
      upstreamTimestamp: params.upstreamTimestamp,
      recordCount: params.recordCount,
    }],
  } satisfies PulseSourceHealth;
  return { ...health, status: resolvePulseSourceHealthStatus(health) };
};

const sourceGap = (source: string, sourceTool: string, error: unknown): PulseSourceHealth => {
  const observedAt = nowIso();
  const gap = toGap(`${sourceTool.toUpperCase()}_FAILED`, error instanceof Error ? error.message : String(error));
  return withSourceHealth({ source, sourceTool, observedAt, upstreamTimestamp: null, recordCount: 0, gaps: [gap] });
};

export const buildPulseWeatherSnapshot = async (
  input: PulseSnapshotInput = {},
): Promise<Pick<PulseSnapshot, "signals" | "sourceHealth" | "gaps">> => {
  const signals: PulseSignal[] = [];
  const sourceHealth: PulseSourceHealth[] = [];

  try {
    const records = await getForecast2Hr(input.area);
    const observedAt = nowIso();
    const upstreamTimestamp = records[0]?.updatedAt ?? records[0]?.validFrom ?? null;
    sourceHealth.push(withSourceHealth({
      source: "NEA",
      sourceTool: "sg_nea_forecast_2hr",
      observedAt,
      upstreamTimestamp,
      recordCount: records.length,
      gaps: records.length === 0 ? [toGap("NEA_FORECAST_EMPTY", "NEA returned no 2-hour forecast rows.")] : [],
    }));
    for (const record of records.slice(0, 12)) {
      const severity = /thundery|heavy|showers|rain/i.test(record.forecast) ? "watch" : "info";
      const freshness = evaluatePulseFreshness({ observedAt, upstreamTimestamp: record.updatedAt ?? record.validFrom, maxAgeSeconds: DEFAULT_MAX_AGE_SECONDS });
      signals.push({
        id: makeId("weather", "forecast", record.area),
        category: "weather",
        severity,
        title: `${record.area}: ${record.forecast}`,
        description: `NEA 2-hour forecast valid ${record.validText}.`,
        source: "NEA",
        sourceTool: "sg_nea_forecast_2hr",
        observedAt,
        upstreamTimestamp: record.updatedAt ?? record.validFrom,
        ...(record.lat === null || record.lng === null ? {} : { location: { lat: record.lat, lng: record.lng } }),
        area: record.area,
        provenance: [{ source: "NEA", sourceTool: "sg_nea_forecast_2hr", observedAt, upstreamTimestamp: record.updatedAt ?? record.validFrom, recordCount: 1 }],
        freshness,
        gaps: [],
        recommendedAction: severity === "watch" ? "Account for near-term wet-weather disruption." : "No weather action required beyond normal monitoring.",
        raw: record,
      });
    }
  } catch (error) {
    sourceHealth.push(sourceGap("NEA", "sg_nea_forecast_2hr", error));
  }

  try {
    const records = await getAirQuality(input.region);
    const observedAt = nowIso();
    const upstreamTimestamp = records[0]?.updatedAt ?? null;
    sourceHealth.push(withSourceHealth({
      source: "NEA",
      sourceTool: "sg_nea_air_quality",
      observedAt,
      upstreamTimestamp,
      recordCount: records.length,
      gaps: records.length === 0 ? [toGap("NEA_AIR_QUALITY_EMPTY", "NEA returned no air-quality rows.")] : [],
    }));
    for (const record of records.slice(0, 6)) {
      const pm25 = record.pm25OneHourly ?? record.pm25TwentyFourHourly ?? 0;
      const severity = pm25 >= 56 ? "disrupted" : pm25 >= 36 ? "watch" : "info";
      const freshness = evaluatePulseFreshness({ observedAt, upstreamTimestamp: record.updatedAt, maxAgeSeconds: DEFAULT_MAX_AGE_SECONDS });
      signals.push({
        id: makeId("weather", "air", record.region),
        category: "weather",
        severity,
        title: `${record.region} PM2.5 ${pm25}`,
        description: `NEA regional air-quality reading with PSI ${record.psi24h ?? "n/a"}.`,
        source: "NEA",
        sourceTool: "sg_nea_air_quality",
        observedAt,
        upstreamTimestamp: record.updatedAt,
        ...(record.lat === null || record.lng === null ? {} : { location: { lat: record.lat, lng: record.lng } }),
        area: record.region,
        provenance: [{ source: "NEA", sourceTool: "sg_nea_air_quality", observedAt, upstreamTimestamp: record.updatedAt, recordCount: 1 }],
        freshness,
        gaps: [],
        recommendedAction: severity === "info" ? "Continue normal monitoring." : "Review outdoor exposure and operational thresholds.",
        raw: record,
      });
    }
  } catch (error) {
    sourceHealth.push(sourceGap("NEA", "sg_nea_air_quality", error));
  }

  try {
    const records = await getRainfall(input.stationId);
    const observedAt = nowIso();
    const upstreamTimestamp = records[0]?.timestamp ?? null;
    sourceHealth.push(withSourceHealth({
      source: "NEA",
      sourceTool: "sg_nea_rainfall",
      observedAt,
      upstreamTimestamp,
      recordCount: records.length,
      gaps: records.length === 0 ? [toGap("NEA_RAINFALL_EMPTY", "NEA returned no rainfall rows.")] : [],
    }));
    for (const record of records.filter((item) => item.value > 0).slice(0, 12)) {
      const severity = record.value >= 10 ? "disrupted" : "watch";
      const freshness = evaluatePulseFreshness({ observedAt, upstreamTimestamp: record.timestamp, maxAgeSeconds: DEFAULT_MAX_AGE_SECONDS });
      signals.push({
        id: makeId("weather", "rainfall", record.stationId),
        category: "weather",
        severity,
        title: `${record.stationName}: ${record.value}${record.unit}`,
        description: "NEA rainfall station reported measurable rain.",
        source: "NEA",
        sourceTool: "sg_nea_rainfall",
        observedAt,
        upstreamTimestamp: record.timestamp,
        ...(record.lat === null || record.lng === null ? {} : { location: { lat: record.lat, lng: record.lng } }),
        area: record.stationName,
        provenance: [{ source: "NEA", sourceTool: "sg_nea_rainfall", observedAt, upstreamTimestamp: record.timestamp, recordCount: 1 }],
        freshness,
        gaps: [],
        recommendedAction: "Check wet-weather plans for affected outdoor routes and sites.",
        raw: record,
      });
    }
  } catch (error) {
    sourceHealth.push(sourceGap("NEA", "sg_nea_rainfall", error));
  }

  return { signals, sourceHealth, gaps: sourceHealth.flatMap((source) => source.gaps) };
};

export const buildPulseMobilitySnapshot = async (): Promise<Pick<PulseSnapshot, "signals" | "sourceHealth" | "gaps">> => {
  const signals: PulseSignal[] = [];
  const sourceHealth: PulseSourceHealth[] = [];

  try {
    const incidents = await getTrafficIncidents();
    const observedAt = nowIso();
    sourceHealth.push(withSourceHealth({ source: "LTA", sourceTool: "sg_lta_traffic_incidents", observedAt, upstreamTimestamp: null, recordCount: incidents.length }));
    for (const incident of incidents.slice(0, 20)) {
      const title = incident.type === "Unknown" ? "Traffic incident" : incident.type;
      const freshness = evaluatePulseFreshness({ observedAt, upstreamTimestamp: null, maxAgeSeconds: DEFAULT_MAX_AGE_SECONDS });
      signals.push({
        id: makeId("mobility", "incident", incident.type, incident.message),
        category: "mobility",
        severity: "watch",
        title,
        description: incident.message || "LTA reported a traffic incident.",
        source: "LTA",
        sourceTool: "sg_lta_traffic_incidents",
        observedAt,
        upstreamTimestamp: null,
        ...(incident.lat === null || incident.lng === null ? {} : { location: { lat: incident.lat, lng: incident.lng } }),
        provenance: [{ source: "LTA", sourceTool: "sg_lta_traffic_incidents", observedAt, upstreamTimestamp: null, recordCount: 1 }],
        freshness,
        gaps: [],
        recommendedAction: "Review route impact before dispatching through the affected corridor.",
        raw: incident,
      });
    }
  } catch (error) {
    sourceHealth.push(sourceGap("LTA", "sg_lta_traffic_incidents", error));
  }

  try {
    const alerts = await getTrainAlerts();
    const observedAt = nowIso();
    const upstreamTimestamp = alerts.messages[0]?.createdDate ?? null;
    sourceHealth.push(withSourceHealth({ source: "LTA", sourceTool: "sg_lta_train_alerts", observedAt, upstreamTimestamp, recordCount: alerts.alerts.length + alerts.messages.length }));
    for (const alert of alerts.alerts) {
      const statusText = alert.status === null ? null : String(alert.status);
      const freshness = evaluatePulseFreshness({ observedAt, upstreamTimestamp, maxAgeSeconds: DEFAULT_MAX_AGE_SECONDS });
      signals.push({
        id: makeId("mobility", "train", alert.line, statusText),
        category: "mobility",
        severity: /disrupt|delay|down/i.test(statusText ?? "") ? "disrupted" : "watch",
        title: `${alert.line} train alert`,
        description: statusText ?? alerts.messages[0]?.content ?? "LTA reported a train service alert.",
        source: "LTA",
        sourceTool: "sg_lta_train_alerts",
        observedAt,
        upstreamTimestamp,
        provenance: [{ source: "LTA", sourceTool: "sg_lta_train_alerts", observedAt, upstreamTimestamp, recordCount: 1 }],
        freshness,
        gaps: [],
        recommendedAction: "Check affected services before recommending transit transfers.",
        raw: alert,
      });
    }
  } catch (error) {
    sourceHealth.push(sourceGap("LTA", "sg_lta_train_alerts", error));
  }

  for (const [sourceTool, loader] of [
    ["sg_lta_road_works", getRoadWorks],
    ["sg_lta_road_openings", getRoadOpenings],
    ["sg_lta_traffic_images", getTrafficImages],
  ] as const) {
    try {
      const records = await loader();
      const observedAt = nowIso();
      const firstRecord = records[0] as { readonly timestamp?: unknown } | undefined;
      const firstTimestamp = typeof firstRecord?.timestamp === "string" ? firstRecord.timestamp : null;
      sourceHealth.push(withSourceHealth({ source: "LTA", sourceTool, observedAt, upstreamTimestamp: firstTimestamp, recordCount: records.length }));
    } catch (error) {
      sourceHealth.push(sourceGap("LTA", sourceTool, error));
    }
  }

  return { signals, sourceHealth, gaps: sourceHealth.flatMap((source) => source.gaps) };
};

export const buildPulseSnapshot = async (input: PulseSnapshotInput = {}): Promise<PulseSnapshot> => {
  const includeMobility = input.focus !== "weather";
  const includeWeather = input.focus !== "mobility";
  const [mobility, weather] = await Promise.all([
    includeMobility ? buildPulseMobilitySnapshot() : Promise.resolve({ signals: [], sourceHealth: [], gaps: [] }),
    includeWeather ? buildPulseWeatherSnapshot(input) : Promise.resolve({ signals: [], sourceHealth: [], gaps: [] }),
  ]);
  return {
    generatedAt: nowIso(),
    focus: input.focus ?? null,
    signals: [...mobility.signals, ...weather.signals],
    sourceHealth: [...mobility.sourceHealth, ...weather.sourceHealth],
    gaps: [...mobility.gaps, ...weather.gaps],
  };
};

export const explainPulseSnapshot = (snapshot: PulseSnapshot): string => {
  const disrupted = snapshot.signals.filter((signal) => signal.severity === "disrupted").length;
  const watch = snapshot.signals.filter((signal) => signal.severity === "watch").length;
  const staleSources = snapshot.sourceHealth.filter((source) => source.status !== "ready").length;
  return [
    `Swee Pulse observed ${snapshot.signals.length} source-backed signals.`,
    `${disrupted} disrupted and ${watch} watch-level signals need attention.`,
    staleSources === 0
      ? "All checked source families reported ready freshness."
      : `${staleSources} source families have freshness gaps or upstream errors.`,
  ].join(" ");
};
