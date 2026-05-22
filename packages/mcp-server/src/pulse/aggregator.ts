import { createHash } from "node:crypto";
import type { EvidenceGap, PulseSignal, PulseSnapshot, PulseSourceHealth } from "@swee-sg/shared";
import {
  getRoadOpenings,
  getRoadWorks,
  getTrafficImages,
  getTrafficIncidents,
  getTrainAlerts,
} from "../apis/lta/client.js";
import { getAirQuality, getForecast2Hr, getRainfall } from "../apis/nea/client.js";

export type PulseSnapshotInput = {
  readonly focus?: string;
  readonly area?: string;
  readonly region?: string;
  readonly stationId?: string;
};

const idFor = (...parts: readonly unknown[]): string =>
  createHash("sha1").update(JSON.stringify(parts)).digest("hex").slice(0, 16);

const toGap = (source: string, error: unknown): EvidenceGap => ({
  code: `${source.toUpperCase()}_UNAVAILABLE`,
  message: error instanceof Error ? error.message : String(error),
});

const sourceHealth = (
  source: string,
  observedAt: string,
  recordCount: number,
  gap?: EvidenceGap,
): PulseSourceHealth => ({
  source,
  status: gap === undefined ? "ready" : "gap",
  observedAt,
  recordCount,
  ...(gap === undefined ? {} : { gap }),
});

const signal = (input: Omit<PulseSignal, "id" | "observedAt" | "provenance"> & {
  readonly observedAt: string;
  readonly provenance?: readonly string[];
}): PulseSignal => ({
  ...input,
  id: idFor(input.category, input.sourceTool, input.title, input.upstreamTimestamp, input.location),
  provenance: input.provenance ?? [input.source],
});

export const buildPulseMobility = async (observedAt = new Date().toISOString()): Promise<{
  readonly signals: readonly PulseSignal[];
  readonly sourceHealth: readonly PulseSourceHealth[];
  readonly gaps: readonly EvidenceGap[];
}> => {
  const signals: PulseSignal[] = [];
  const health: PulseSourceHealth[] = [];
  const gaps: EvidenceGap[] = [];

  try {
    const train = await getTrainAlerts();
    for (const alert of train.alerts) {
      signals.push(signal({
        category: "mobility",
        severity: alert.status?.toLowerCase() === "normal" ? "info" : "disrupted",
        title: `Train alert on ${alert.line}`,
        description: alert.status ?? "Train service alert reported by LTA.",
        source: "LTA DataMall",
        sourceTool: "sg_lta_train_alerts",
        observedAt,
        upstreamTimestamp: train.messages[0]?.createdDate ?? null,
        recommendedAction: "Check affected stations and plan a fallback route before departure.",
        raw: alert,
      }));
    }
    health.push(sourceHealth("LTA train alerts", observedAt, train.alerts.length));
  } catch (error) {
    const gap = toGap("lta_train_alerts", error);
    gaps.push(gap);
    health.push(sourceHealth("LTA train alerts", observedAt, 0, gap));
  }

  try {
    const incidents = await getTrafficIncidents();
    for (const item of incidents.slice(0, 20)) {
      signals.push(signal({
        category: "mobility",
        severity: "watch",
        title: item.type,
        description: item.message || "Traffic incident reported by LTA.",
        source: "LTA DataMall",
        sourceTool: "sg_lta_traffic_incidents",
        observedAt,
        upstreamTimestamp: null,
        location: item.lat === null || item.lng === null ? undefined : { lat: item.lat, lng: item.lng },
        recommendedAction: "Avoid affected roads or monitor before dispatching.",
        raw: item,
      }));
    }
    health.push(sourceHealth("LTA traffic incidents", observedAt, incidents.length));
  } catch (error) {
    const gap = toGap("lta_traffic_incidents", error);
    gaps.push(gap);
    health.push(sourceHealth("LTA traffic incidents", observedAt, 0, gap));
  }

  try {
    const [works, openings, cameras] = await Promise.all([
      getRoadWorks(),
      getRoadOpenings(),
      getTrafficImages(),
    ]);
    for (const item of [...works.slice(0, 10), ...openings.slice(0, 10)]) {
      signals.push(signal({
        category: "mobility",
        severity: "watch",
        title: item.roadName ?? item.eventType,
        description: item.message || `${item.eventType} reported by LTA.`,
        source: "LTA DataMall",
        sourceTool: item.eventType === "road-work" ? "sg_lta_road_works" : "sg_lta_road_openings",
        observedAt,
        upstreamTimestamp: item.startTime,
        location: item.lat === null || item.lng === null ? undefined : { lat: item.lat, lng: item.lng },
        recommendedAction: "Check timing and route impact before field movement.",
        raw: item,
      }));
    }
    health.push(sourceHealth("LTA road events", observedAt, works.length + openings.length));
    health.push(sourceHealth("data.gov.sg traffic images", observedAt, cameras.length));
  } catch (error) {
    const gap = toGap("lta_road_events", error);
    gaps.push(gap);
    health.push(sourceHealth("LTA road events", observedAt, 0, gap));
  }

  return { signals, sourceHealth: health, gaps };
};

export const buildPulseWeather = async (
  input: PulseSnapshotInput = {},
  observedAt = new Date().toISOString(),
): Promise<{
  readonly signals: readonly PulseSignal[];
  readonly sourceHealth: readonly PulseSourceHealth[];
  readonly gaps: readonly EvidenceGap[];
}> => {
  const signals: PulseSignal[] = [];
  const health: PulseSourceHealth[] = [];
  const gaps: EvidenceGap[] = [];

  try {
    const forecasts = await getForecast2Hr(input.area);
    for (const item of forecasts.slice(0, input.area === undefined ? 12 : 4)) {
      const wet = /rain|showers|thundery/i.test(item.forecast);
      signals.push(signal({
        category: "weather",
        severity: wet ? "watch" : "info",
        title: `${item.area}: ${item.forecast}`,
        description: item.validText ?? `Forecast valid from ${item.validFrom} to ${item.validTo}.`,
        source: "NEA",
        sourceTool: "sg_nea_forecast_2hr",
        observedAt,
        upstreamTimestamp: item.updatedAt,
        location: item.lat === null || item.lng === null ? undefined : { lat: item.lat, lng: item.lng },
        area: item.area,
        recommendedAction: wet ? "Prepare wet-weather fallback for outdoor or transport-sensitive work." : "Monitor for changes before time-sensitive movement.",
        raw: item,
      }));
    }
    health.push(sourceHealth("NEA 2-hour forecast", observedAt, forecasts.length));
  } catch (error) {
    const gap = toGap("nea_forecast", error);
    gaps.push(gap);
    health.push(sourceHealth("NEA 2-hour forecast", observedAt, 0, gap));
  }

  try {
    const air = await getAirQuality(input.region);
    for (const item of air) {
      const psi = item.psi24h ?? 0;
      signals.push(signal({
        category: "weather",
        severity: psi > 100 ? "disrupted" : psi > 50 ? "watch" : "info",
        title: `${item.region} PSI ${item.psi24h ?? "unknown"}`,
        description: `PM2.5 one-hour reading: ${item.pm25OneHourly ?? "unknown"}.`,
        source: "NEA",
        sourceTool: "sg_nea_air_quality",
        observedAt,
        upstreamTimestamp: item.updatedAt,
        location: item.lat === null || item.lng === null ? undefined : { lat: item.lat, lng: item.lng },
        area: item.region,
        recommendedAction: psi > 100 ? "Review outdoor exposure and operational contingencies." : "Continue monitoring air quality.",
        raw: item,
      }));
    }
    health.push(sourceHealth("NEA air quality", observedAt, air.length));
  } catch (error) {
    const gap = toGap("nea_air_quality", error);
    gaps.push(gap);
    health.push(sourceHealth("NEA air quality", observedAt, 0, gap));
  }

  try {
    const rainfall = await getRainfall(input.stationId);
    for (const item of rainfall.filter((reading) => reading.value > 0).slice(0, 20)) {
      signals.push(signal({
        category: "weather",
        severity: item.value > 10 ? "disrupted" : "watch",
        title: `${item.stationName}: ${item.value} ${item.unit}`,
        description: `Rainfall observed at ${item.stationName}.`,
        source: "NEA",
        sourceTool: "sg_nea_rainfall",
        observedAt,
        upstreamTimestamp: item.timestamp,
        location: item.lat === null || item.lng === null ? undefined : { lat: item.lat, lng: item.lng },
        area: item.stationName,
        recommendedAction: "Check drainage, traffic, and outdoor activity plans near this station.",
        raw: item,
      }));
    }
    health.push(sourceHealth("NEA rainfall", observedAt, rainfall.length));
  } catch (error) {
    const gap = toGap("nea_rainfall", error);
    gaps.push(gap);
    health.push(sourceHealth("NEA rainfall", observedAt, 0, gap));
  }

  return { signals, sourceHealth: health, gaps };
};

export const buildPulseSnapshot = async (input: PulseSnapshotInput = {}): Promise<PulseSnapshot> => {
  const generatedAt = new Date().toISOString();
  const [mobility, weather] = await Promise.all([
    buildPulseMobility(generatedAt),
    buildPulseWeather(input, generatedAt),
  ]);
  return {
    generatedAt,
    focus: input.focus ?? input.area ?? input.region ?? input.stationId ?? null,
    signals: [...mobility.signals, ...weather.signals].sort((left, right) =>
      severityRank(right.severity) - severityRank(left.severity),
    ),
    sourceHealth: [...mobility.sourceHealth, ...weather.sourceHealth],
    gaps: [...mobility.gaps, ...weather.gaps],
  };
};

const severityRank = (severity: PulseSignal["severity"]): number => {
  if (severity === "critical") return 4;
  if (severity === "disrupted") return 3;
  if (severity === "watch") return 2;
  return 1;
};

export const explainPulseSnapshot = (snapshot: PulseSnapshot): string => {
  const disrupted = snapshot.signals.filter((signalItem) => signalItem.severity === "critical" || signalItem.severity === "disrupted");
  const watch = snapshot.signals.filter((signalItem) => signalItem.severity === "watch");
  const top = [...disrupted, ...watch].slice(0, 5);
  if (top.length === 0) {
    return `Swee Pulse found no disrupted or watch-level Singapore mobility/weather signals at ${snapshot.generatedAt}. Review source freshness before operational decisions.`;
  }
  return [
    `Swee Pulse found ${disrupted.length} disrupted and ${watch.length} watch-level signals at ${snapshot.generatedAt}.`,
    `Top signals: ${top.map((signalItem) => `${signalItem.title} (${signalItem.source})`).join("; ")}.`,
    snapshot.gaps.length === 0
      ? "No source gaps were reported."
      : `Source gaps: ${snapshot.gaps.map((gap) => gap.code).join(", ")}.`,
  ].join(" ");
};
