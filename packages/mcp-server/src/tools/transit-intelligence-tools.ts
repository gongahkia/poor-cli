import { randomUUID } from "node:crypto";
import {
  BriefArtifactSchema,
  TransitAccessibleRouteSchema,
  TransitCounterfactualSimulateSchema,
  TransitHealthSchema,
  TransitHotspotsSchema,
  TransitModelMetricsSchema,
  TransitObjectivePlanSchema,
  TransitOpsBriefSchema,
  TransitOutcomeRecordSchema,
  TransitPackSchema,
  TransitPolicyAuditSchema,
  TransitPolicyReplaySchema,
  TransitReliabilitySchema,
  TransitTransferRiskSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@swee-sg/shared";
import type { BriefArtifact, OutputFormat, ToolResult } from "@swee-sg/shared";
import {
  getBusArrivals,
  getBusStopLookups,
  getRoadOpenings,
  getRoadWorks,
  getTrafficImages,
  getTrafficIncidents,
  getTrainAlerts,
} from "../apis/lta/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

type TransitServicePlan = {
  readonly serviceNo: string;
  readonly etaMinutes: number | null;
  readonly load: string | null;
  readonly confidence: number;
  readonly rationale: string;
};

type TransitSnapshot = {
  readonly generatedAt: string;
  readonly stopIds: readonly string[];
  readonly stopLookups: Readonly<Record<string, { readonly name: string | null; readonly roadName: string | null; readonly lat: number | null; readonly lng: number | null }>>;
  readonly arrivalBoards: Readonly<Record<string, readonly Readonly<Record<string, unknown>>[]>>;
  readonly trainAlerts: readonly Readonly<Record<string, unknown>>[];
  readonly trainMessages: readonly Readonly<Record<string, unknown>>[];
  readonly trafficIncidents: readonly Readonly<Record<string, unknown>>[];
  readonly roadEvents: readonly Readonly<Record<string, unknown>>[];
  readonly trafficImages: readonly Readonly<Record<string, unknown>>[];
};

type TransitHealth = {
  readonly generatedAt: string;
  readonly summary: {
    readonly stopCount: number;
    readonly serviceCount: number;
    readonly averageScore: number;
    readonly criticalStopCount: number;
    readonly worstStopId: string | null;
    readonly worstStopScore: number | null;
  };
  readonly context: {
    readonly disruptedLineCount: number;
    readonly incidentCount: number;
    readonly roadEventCount: number;
    readonly cameraCount: number;
  };
  readonly stops: readonly Readonly<Record<string, unknown>>[];
};

type TransitHotspots = {
  readonly generatedAt: string;
  readonly summary: {
    readonly hotspotCount: number;
    readonly severeHotspotCount: number;
    readonly highHotspotCount: number;
    readonly impactedWatchStopCount: number;
  };
  readonly hotspots: readonly TransitHotspot[];
};

type TransitHotspot = {
  readonly hotspotId: string;
  readonly level: "severe" | "high" | "medium" | "low";
  readonly riskScore: number;
  readonly position: {
    readonly lat: number;
    readonly lng: number;
  };
  readonly incidentCount: number;
  readonly highSeverityIncidentCount: number;
  readonly roadEventCount: number;
  readonly cameraCount: number;
  readonly nearbyStops: readonly {
    readonly stopId: string;
    readonly stopName: string;
    readonly roadName: string | null;
    readonly distanceMeters: number;
  }[];
  readonly highlights: readonly string[];
};

type TransitBriefing = {
  readonly generatedAt: string;
  readonly scopeKey: string;
  readonly headline: string;
  readonly trend: "improving" | "stable" | "worsening" | "unknown";
  readonly riskIndex: number;
  readonly metrics: Readonly<Record<string, unknown>>;
  readonly actionItems: readonly Readonly<Record<string, unknown>>[];
};

type TransitPack = {
  readonly generatedAt: string;
  readonly snapshot: TransitSnapshot;
  readonly health: TransitHealth;
  readonly hotspots: TransitHotspots;
  readonly briefing: TransitBriefing;
};

type TransitObjective = "minimize_delay" | "maximize_accessibility" | "minimize_transfer_risk" | "balanced";
type TransitMobilityMode = "wheelchair" | "reduced-walk" | "elder-friendly";

type TransitPlanDecision = {
  readonly id: string;
  readonly score: number;
  readonly confidence: number;
  readonly title: string;
  readonly detail: string;
  readonly actions: readonly Readonly<Record<string, unknown>>[];
  readonly references: readonly Readonly<Record<string, unknown>>[];
};

type TransitPolicyViolation = {
  readonly rule: string;
  readonly reason: string;
};

type TransitObjectivePlan = {
  readonly generatedAt: string;
  readonly tenantId: string;
  readonly scopeKey: string;
  readonly objective: TransitObjective;
  readonly riskIndex: number;
  readonly trend: "improving" | "stable" | "worsening" | "unknown";
  readonly decisions: readonly TransitPlanDecision[];
  readonly blockedByPolicies: readonly TransitPolicyViolation[];
  readonly explainers: readonly string[];
};

type TransitPolicyEvaluation = {
  readonly decisionId: string;
  readonly status: "accepted" | "blocked";
  readonly rule: "accepted" | "min-confidence" | "max-walk-meters" | "avoid-high-risk" | "wheelchair-accessibility";
  readonly reason: string;
  readonly score: number;
  readonly confidence: number;
  readonly riskLevel: "low" | "medium" | "high";
};

type TransitTenantProfile = {
  readonly tenantId: string;
  readonly name: string;
  readonly defaultObjective: TransitObjective;
  readonly weights: {
    readonly reliability: number;
    readonly transferRisk: number;
    readonly accessibility: number;
    readonly operations: number;
  };
  readonly guardrails: {
    readonly maxWalkMeters: number;
    readonly minConfidence: number;
    readonly avoidHighRisk: boolean;
    readonly requireWheelchairAccessibleForMode: boolean;
  };
  readonly thresholds: {
    readonly highRiskIndex: number;
    readonly webhookTriggerRiskIndex: number;
  };
  readonly updatedAt: string;
};

type TransitTenantMemory = {
  readonly tenantId: string;
  readonly scopeKey: string;
  readonly updatedAt: string;
  readonly latestRiskIndex: number;
  readonly trend: "improving" | "stable" | "worsening" | "unknown";
  readonly lastDecisionIds: readonly string[];
};

type TransitOutcomeEvent = {
  readonly id: string;
  readonly timestamp: string;
  readonly scopeKey?: string;
  readonly recommendationType: "reliability" | "transfer-risk" | "playbook" | "accessibility";
  readonly recommendationId?: string;
  readonly accepted: boolean;
  readonly success?: boolean;
  readonly confidence?: number;
  readonly predictedWaitMinutes?: number;
  readonly actualWaitMinutes?: number;
  readonly predictedRisk?: number;
  readonly actualRisk?: number;
  readonly metadata?: Readonly<Record<string, unknown>>;
};

type TransitPolicyAuditRecord = {
  readonly traceId: string;
  readonly timestamp: string;
  readonly tenantId: string;
  readonly scopeKey: string;
  readonly source: "plan" | "counterfactual-baseline" | "counterfactual-scenario" | "policy-replay";
  readonly objective: TransitObjective;
  readonly riskIndex: number;
  readonly trend: "improving" | "stable" | "worsening" | "unknown";
  readonly request: Readonly<Record<string, unknown>>;
  readonly guardrails: Readonly<Record<string, unknown>>;
  readonly thresholds: Readonly<Record<string, unknown>>;
  readonly weights: Readonly<Record<string, unknown>>;
  readonly policyEvaluations: readonly TransitPolicyEvaluation[];
  readonly acceptedDecisionIds: readonly string[];
  readonly blockedByPolicies: readonly TransitPolicyViolation[];
  readonly metadata?: Readonly<Record<string, unknown>>;
};

const DEFAULT_SCOPE_KEY = "transit-default";
const DEFAULT_TENANT_ID = "default";

const scopeRiskMemory = new Map<string, number>();
const tenantProfiles = new Map<string, TransitTenantProfile>();
const tenantMemories = new Map<string, TransitTenantMemory>();
const policyAuditRecords: TransitPolicyAuditRecord[] = [];
const outcomeEvents: TransitOutcomeEvent[] = [];

const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value));
const round = (value: number, precision = 2): number => {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
};

const toIsoNow = (): string => new Date().toISOString();

const toMinutesUntil = (timestamp: string | null): number | null => {
  if (timestamp === null) {
    return null;
  }
  const diffMs = new Date(timestamp).getTime() - Date.now();
  const mins = diffMs / 60000;
  return Number.isFinite(mins) ? round(mins, 1) : null;
};

const toTrend = (previous: number | undefined, next: number): "improving" | "stable" | "worsening" | "unknown" => {
  if (previous === undefined) {
    return "unknown";
  }
  const delta = next - previous;
  if (delta >= 3) {
    return "worsening";
  }
  if (delta <= -3) {
    return "improving";
  }
  return "stable";
};

const getDefaultTenantProfile = (tenantId: string): TransitTenantProfile => ({
  tenantId,
  name: tenantId === DEFAULT_TENANT_ID ? "Default Tenant" : `Tenant ${tenantId}`,
  defaultObjective: "balanced",
  weights: {
    reliability: 1,
    transferRisk: 1,
    accessibility: 1,
    operations: 1,
  },
  guardrails: {
    maxWalkMeters: 900,
    minConfidence: 0.35,
    avoidHighRisk: false,
    requireWheelchairAccessibleForMode: true,
  },
  thresholds: {
    highRiskIndex: 60,
    webhookTriggerRiskIndex: 70,
  },
  updatedAt: toIsoNow(),
});

const getTenantProfile = (tenantIdRaw: string | undefined): TransitTenantProfile => {
  const tenantId = (tenantIdRaw ?? DEFAULT_TENANT_ID).trim() || DEFAULT_TENANT_ID;
  const existing = tenantProfiles.get(tenantId);
  if (existing !== undefined) {
    return existing;
  }
  const created = getDefaultTenantProfile(tenantId);
  tenantProfiles.set(tenantId, created);
  return created;
};

const upsertTenantMemory = (tenantId: string, scopeKey: string, riskIndex: number, trend: TransitBriefing["trend"], decisionIds: readonly string[]): TransitTenantMemory => {
  const next: TransitTenantMemory = {
    tenantId,
    scopeKey,
    updatedAt: toIsoNow(),
    latestRiskIndex: riskIndex,
    trend,
    lastDecisionIds: [...decisionIds],
  };
  tenantMemories.set(`${tenantId}:${scopeKey}`, next);
  return next;
};

const getTenantMemory = (tenantId: string, scopeKey: string): TransitTenantMemory | undefined => {
  return tenantMemories.get(`${tenantId}:${scopeKey}`);
};

const getBestEtaMinutes = (service: Readonly<Record<string, unknown>>): number | null => {
  const arrivals = Array.isArray(service["arrivals"]) ? service["arrivals"] as readonly Readonly<Record<string, unknown>>[] : [];
  const best = arrivals
    .map((arrival) => typeof arrival["estimatedArrival"] === "string" ? toMinutesUntil(arrival["estimatedArrival"] as string) : null)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
    .filter((value) => value >= 0)
    .sort((left, right) => left - right)[0];
  return best ?? null;
};

const parseLoadPenalty = (load: string | null): number => {
  const normalized = (load ?? "").trim().toUpperCase();
  if (normalized === "LSD") {
    return 10;
  }
  if (normalized === "SDA") {
    return 5;
  }
  return 0;
};

const getIncidentSeverity = (type: string): "low" | "moderate" | "high" | "unknown" => {
  const normalized = type.trim().toLowerCase();
  if (normalized.includes("accident") || normalized.includes("breakdown") || normalized.includes("road block")) {
    return "high";
  }
  if (normalized.includes("heavy traffic") || normalized.includes("obstacle") || normalized.includes("weather")) {
    return "moderate";
  }
  if (normalized.length > 0) {
    return "low";
  }
  return "unknown";
};

const toRiskLevel = (score: number): "low" | "medium" | "high" => {
  if (score >= 75) {
    return "low";
  }
  if (score >= 50) {
    return "medium";
  }
  return "high";
};

const toHealthGrade = (score: number): "excellent" | "good" | "fair" | "poor" | "critical" => {
  if (score >= 85) return "excellent";
  if (score >= 70) return "good";
  if (score >= 55) return "fair";
  if (score >= 40) return "poor";
  return "critical";
};

const toHotspotLevel = (riskScore: number): "severe" | "high" | "medium" | "low" => {
  if (riskScore >= 80) return "severe";
  if (riskScore >= 60) return "high";
  if (riskScore >= 35) return "medium";
  return "low";
};

const haversineMeters = (
  left: Readonly<{ lat: number; lng: number }>,
  right: Readonly<{ lat: number; lng: number }>,
): number => {
  const toRad = (value: number): number => (value * Math.PI) / 180;
  const earthRadiusMeters = 6371000;
  const dLat = toRad(right.lat - left.lat);
  const dLng = toRad(right.lng - left.lng);
  const lat1 = toRad(left.lat);
  const lat2 = toRad(right.lat);
  const a =
    Math.sin(dLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return earthRadiusMeters * c;
};

const buildSnapshot = async (
  params: Readonly<{ stopIds?: readonly string[] | undefined; includeTrafficImages?: boolean | undefined }>,
): Promise<TransitSnapshot> => {
  const stopIds = Array.from(new Set((params.stopIds ?? []).filter((value) => /^\d{5}$/.test(value))));

  const [trainAlerts, trafficIncidents, roadWorks, roadOpenings, trafficImages, stopLookupsRaw] = await Promise.all([
    getTrainAlerts(),
    getTrafficIncidents(),
    getRoadWorks(),
    getRoadOpenings(),
    params.includeTrafficImages === false ? Promise.resolve([]) : getTrafficImages(),
    getBusStopLookups(stopIds),
  ]);

  const boards = await Promise.all(stopIds.map(async (stopId) => ({
    stopId,
    services: await getBusArrivals(stopId),
  })));

  const arrivalBoards: Record<string, readonly Readonly<Record<string, unknown>>[]> = {};
  for (const board of boards) {
    arrivalBoards[board.stopId] = board.services as readonly Readonly<Record<string, unknown>>[];
  }

  const stopLookups: Record<string, { name: string | null; roadName: string | null; lat: number | null; lng: number | null }> = {};
  for (const [stopId, lookup] of Object.entries(stopLookupsRaw)) {
    stopLookups[stopId] = {
      name: lookup.description,
      roadName: lookup.roadName,
      lat: lookup.lat,
      lng: lookup.lng,
    };
  }

  return {
    generatedAt: toIsoNow(),
    stopIds,
    stopLookups,
    arrivalBoards,
    trainAlerts: trainAlerts.alerts as readonly Readonly<Record<string, unknown>>[],
    trainMessages: trainAlerts.messages as readonly Readonly<Record<string, unknown>>[],
    trafficIncidents: trafficIncidents as readonly Readonly<Record<string, unknown>>[],
    roadEvents: [...roadWorks, ...roadOpenings] as readonly Readonly<Record<string, unknown>>[],
    trafficImages: trafficImages as readonly Readonly<Record<string, unknown>>[],
  };
};

const buildHealth = (snapshot: TransitSnapshot): TransitHealth => {
  const disruptedLineCount = snapshot.trainAlerts.filter((alert) => Number(alert["status"]) === 2 || String(alert["status"]).toLowerCase() === "disrupted").length;
  const incidentCount = snapshot.trafficIncidents.length;
  const roadEventCount = snapshot.roadEvents.length;
  const cameraCount = snapshot.trafficImages.length;

  const globalPenalty = clamp(disruptedLineCount * 1.5 + incidentCount * 0.9 + roadEventCount * 0.5, 0, 20);

  const stops = snapshot.stopIds.map((stopId) => {
    const services = snapshot.arrivalBoards[stopId] ?? [];
    const serviceInsights = services.map((service) => {
      const etaMinutes = getBestEtaMinutes(service);
      const arrivals = Array.isArray(service["arrivals"]) ? service["arrivals"] as readonly Readonly<Record<string, unknown>>[] : [];
      const load = typeof arrivals[0]?.["load"] === "string" ? String(arrivals[0]?.["load"]) : null;
      const etaPenalty = etaMinutes === null
        ? 45
        : etaMinutes >= 20
          ? 22 + (etaMinutes - 20) * 2
          : etaMinutes >= 12
            ? 10 + (etaMinutes - 12) * 1.8
            : etaMinutes * 0.55;
      const score = round(clamp(100 - etaPenalty - parseLoadPenalty(load), 0, 100), 1);
      return {
        serviceNo: typeof service["serviceNo"] === "string" ? service["serviceNo"] : "unknown",
        bestEtaMinutes: etaMinutes,
        primaryLoad: load,
        score,
        grade: toHealthGrade(score),
      };
    });

    const serviceScores = serviceInsights.map((service) => service.score);
    const baseScore = serviceScores.length === 0
      ? 30
      : serviceScores.reduce((sum, value) => sum + value, 0) / serviceScores.length;
    const stopScore = round(clamp(baseScore - globalPenalty, 0, 100), 1);

    const quickWins = serviceInsights
      .filter((service) => typeof service.bestEtaMinutes === "number" && service.bestEtaMinutes <= 12)
      .sort((left, right) => (left.bestEtaMinutes ?? Number.POSITIVE_INFINITY) - (right.bestEtaMinutes ?? Number.POSITIVE_INFINITY))
      .slice(0, 3)
      .map((service) => `Take ${service.serviceNo} in ${service.bestEtaMinutes}m${service.primaryLoad ? ` (${service.primaryLoad})` : ""}`);

    return {
      stopId,
      stopName: snapshot.stopLookups[stopId]?.name ?? stopId,
      roadName: snapshot.stopLookups[stopId]?.roadName ?? null,
      score: stopScore,
      grade: toHealthGrade(stopScore),
      services: serviceInsights.sort((left, right) => left.score - right.score),
      quickWins,
    };
  }).sort((left, right) => left.score - right.score);

  const averageScore = stops.length === 0
    ? 0
    : round(stops.reduce((sum, stop) => sum + stop.score, 0) / stops.length, 1);

  return {
    generatedAt: toIsoNow(),
    summary: {
      stopCount: stops.length,
      serviceCount: stops.reduce((sum, stop) => sum + stop.services.length, 0),
      averageScore,
      criticalStopCount: stops.filter((stop) => stop.grade === "critical").length,
      worstStopId: stops[0]?.stopId ?? null,
      worstStopScore: stops[0]?.score ?? null,
    },
    context: {
      disruptedLineCount,
      incidentCount,
      roadEventCount,
      cameraCount,
    },
    stops,
  };
};

const buildHotspots = (
  snapshot: TransitSnapshot,
  options?: Readonly<{ gridSizeDegrees?: number | undefined; impactRadiusMeters?: number | undefined }>,
): TransitHotspots => {
  const gridSize = options?.gridSizeDegrees ?? 0.0038;
  const impactRadiusMeters = options?.impactRadiusMeters ?? 850;

  type Bucket = {
    readonly key: string;
    latSum: number;
    lngSum: number;
    count: number;
    incidentCount: number;
    highSeverityIncidentCount: number;
    roadEventCount: number;
    cameraCount: number;
    riskSum: number;
  };

  const buckets = new Map<string, Bucket>();

  const addPoint = (
    lat: number,
    lng: number,
    category: "incident" | "road-event" | "camera",
    riskWeight: number,
    highSeverityIncident = false,
  ): void => {
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return;
    }
    const key = `${Math.floor(lat / gridSize)}:${Math.floor(lng / gridSize)}`;
    const existing = buckets.get(key);
    if (existing === undefined) {
      buckets.set(key, {
        key,
        latSum: lat,
        lngSum: lng,
        count: 1,
        incidentCount: category === "incident" ? 1 : 0,
        highSeverityIncidentCount: highSeverityIncident ? 1 : 0,
        roadEventCount: category === "road-event" ? 1 : 0,
        cameraCount: category === "camera" ? 1 : 0,
        riskSum: riskWeight,
      });
      return;
    }

    existing.latSum += lat;
    existing.lngSum += lng;
    existing.count += 1;
    existing.riskSum += riskWeight;
    if (category === "incident") {
      existing.incidentCount += 1;
      if (highSeverityIncident) {
        existing.highSeverityIncidentCount += 1;
      }
    } else if (category === "road-event") {
      existing.roadEventCount += 1;
    } else {
      existing.cameraCount += 1;
    }
  };

  for (const incident of snapshot.trafficIncidents) {
    const type = typeof incident["type"] === "string" ? incident["type"] : "";
    const severity = getIncidentSeverity(type);
    const weight = severity === "high" ? 28 : severity === "moderate" ? 16 : 8;
    const lat = typeof incident["lat"] === "number" ? incident["lat"] : null;
    const lng = typeof incident["lng"] === "number" ? incident["lng"] : null;
    if (lat !== null && lng !== null) {
      addPoint(lat, lng, "incident", weight, severity === "high");
    }
  }

  for (const roadEvent of snapshot.roadEvents) {
    const lat = typeof roadEvent["lat"] === "number" ? roadEvent["lat"] : null;
    const lng = typeof roadEvent["lng"] === "number" ? roadEvent["lng"] : null;
    if (lat !== null && lng !== null) {
      addPoint(lat, lng, "road-event", 10);
    }
  }

  for (const camera of snapshot.trafficImages) {
    const lat = typeof camera["lat"] === "number" ? camera["lat"] : null;
    const lng = typeof camera["lng"] === "number" ? camera["lng"] : null;
    if (lat !== null && lng !== null) {
      addPoint(lat, lng, "camera", 3);
    }
  }

  const stopReferences = Object.entries(snapshot.stopLookups)
    .filter(([, value]) => typeof value.lat === "number" && typeof value.lng === "number")
    .map(([id, value]) => ({
      id,
      name: value.name ?? id,
      roadName: value.roadName,
      lat: value.lat as number,
      lng: value.lng as number,
    }));

  const hotspots: TransitHotspot[] = Array.from(buckets.values()).map((bucket) => {
    const lat = bucket.latSum / bucket.count;
    const lng = bucket.lngSum / bucket.count;
    const riskScore = round(clamp(bucket.riskSum, 0, 100), 1);
    const level = toHotspotLevel(riskScore);

    const nearbyStops = stopReferences
      .map((stop) => ({
        stopId: stop.id,
        stopName: stop.name,
        roadName: stop.roadName,
        distanceMeters: round(haversineMeters({ lat, lng }, { lat: stop.lat, lng: stop.lng }), 1),
      }))
      .filter((stop) => stop.distanceMeters <= impactRadiusMeters)
      .sort((left, right) => left.distanceMeters - right.distanceMeters)
      .slice(0, 6);

    const highlights: string[] = [];
    if (bucket.highSeverityIncidentCount > 0) {
      highlights.push(`${bucket.highSeverityIncidentCount} high-severity incident(s)`);
    }
    if (bucket.roadEventCount > 0) {
      highlights.push(`${bucket.roadEventCount} road event(s)`);
    }
    if (bucket.cameraCount > 0) {
      highlights.push(`${bucket.cameraCount} traffic camera(s)`);
    }

    return {
      hotspotId: `hotspot-${bucket.key}`,
      level,
      riskScore,
      position: { lat: round(lat, 6), lng: round(lng, 6) },
      incidentCount: bucket.incidentCount,
      highSeverityIncidentCount: bucket.highSeverityIncidentCount,
      roadEventCount: bucket.roadEventCount,
      cameraCount: bucket.cameraCount,
      nearbyStops,
      highlights,
    };
  }).sort((left, right) => right.riskScore - left.riskScore);

  const impactedWatchStops = new Set(
    hotspots.flatMap((hotspot) => hotspot.nearbyStops.map((stop) => stop.stopId)),
  );

  return {
    generatedAt: toIsoNow(),
    summary: {
      hotspotCount: hotspots.length,
      severeHotspotCount: hotspots.filter((hotspot) => hotspot.level === "severe").length,
      highHotspotCount: hotspots.filter((hotspot) => hotspot.level === "high").length,
      impactedWatchStopCount: impactedWatchStops.size,
    },
    hotspots,
  };
};

const buildOpsBriefing = (
  health: TransitHealth,
  hotspots: TransitHotspots,
  scopeKey: string,
): TransitBriefing => {
  const criticalStopCount = health.summary.criticalStopCount;
  const severeHotspotCount = hotspots.summary.severeHotspotCount;
  const highHotspotCount = hotspots.summary.highHotspotCount;
  const disruptedLineCount = health.context.disruptedLineCount;
  const incidentCount = health.context.incidentCount;

  const riskIndex = round(clamp(
    criticalStopCount * 16
      + severeHotspotCount * 22
      + highHotspotCount * 12
      + disruptedLineCount * 10
      + incidentCount * 3,
    0,
    100,
  ), 1);

  const previous = scopeRiskMemory.get(scopeKey);
  const trend = toTrend(previous, riskIndex);
  scopeRiskMemory.set(scopeKey, riskIndex);

  const actionItems: Array<Readonly<Record<string, unknown>>> = [];
  const worstStop = health.stops[0];
  if (worstStop !== undefined) {
    actionItems.push({
      id: "action-worst-stop",
      priority: worstStop["grade"] === "critical" ? "high" : "medium",
      title: `Monitor stop ${String(worstStop["stopId"] ?? "unknown")}`,
      detail: `Current health score ${String(worstStop["score"] ?? "n/a")} at ${String(worstStop["stopName"] ?? "the stop")}.`,
      relatedStopId: worstStop["stopId"],
    });
  }

  const topHotspot = hotspots.hotspots[0];
  if (topHotspot !== undefined) {
    actionItems.push({
      id: "action-top-hotspot",
      priority: topHotspot.level === "severe" ? "high" : "medium",
      title: `Investigate ${topHotspot.level} hotspot`,
      detail: `${topHotspot.highlights.join("; ") || "Transport disruption signals detected"}.`,
      relatedHotspotId: topHotspot.hotspotId,
    });
  }

  if (disruptedLineCount > 0) {
    actionItems.push({
      id: "action-train-alerts",
      priority: "high",
      title: "Escalate disrupted train lines",
      detail: `${disruptedLineCount} disrupted train alert(s) active; coordinate rider communication and diversion messaging.`,
    });
  }

  const headline = riskIndex >= 70
    ? "High transit operational risk detected"
    : riskIndex >= 45
      ? "Moderate transit operational risk detected"
      : "Transit operations currently stable";

  return {
    generatedAt: toIsoNow(),
    scopeKey,
    headline,
    trend,
    riskIndex,
    metrics: {
      averageHealthScore: health.summary.averageScore,
      criticalStopCount,
      severeHotspotCount,
      highHotspotCount,
      disruptedLineCount,
      incidentCount,
    },
    actionItems,
  };
};

const buildPack = async (
  params: Readonly<{ stopIds?: readonly string[] | undefined; scopeKey?: string | undefined; includeTrafficImages?: boolean | undefined }>,
): Promise<TransitPack> => {
  const snapshot = await buildSnapshot(params);
  const health = buildHealth(snapshot);
  const hotspots = buildHotspots(snapshot);
  const briefing = buildOpsBriefing(health, hotspots, params.scopeKey ?? DEFAULT_SCOPE_KEY);
  return {
    generatedAt: toIsoNow(),
    snapshot,
    health,
    hotspots,
    briefing,
  };
};

const buildReliability = (
  snapshot: TransitSnapshot,
  params: Readonly<{ originStopId: string; destinationStopId: string; horizonMinutes?: number | undefined }>,
): Readonly<Record<string, unknown>> => {
  const originServices = snapshot.arrivalBoards[params.originStopId] ?? [];
  const destinationServices = snapshot.arrivalBoards[params.destinationStopId] ?? [];
  const horizonMinutes = Math.max(15, params.horizonMinutes ?? 45);

  const plans: TransitServicePlan[] = originServices.map((service) => {
    const etaMinutes = getBestEtaMinutes(service);
    const arrivals = Array.isArray(service["arrivals"]) ? service["arrivals"] as readonly Readonly<Record<string, unknown>>[] : [];
    const load = typeof arrivals[0]?.["load"] === "string" ? String(arrivals[0]?.["load"]) : null;
    const liveCount = arrivals.filter((arrival) => typeof arrival["estimatedArrival"] === "string").length;
    const confidence = round(clamp(0.45 + liveCount * 0.18 - parseLoadPenalty(load) / 20, 0.2, 0.96), 3);
    return {
      serviceNo: typeof service["serviceNo"] === "string" ? service["serviceNo"] : "unknown",
      etaMinutes,
      load,
      confidence,
      rationale: etaMinutes === null
        ? "No live ETA yet; use as backup option."
        : load?.toUpperCase() === "LSD"
          ? `Arrives in ${etaMinutes}m but expected to be crowded.`
          : `Arrives in ${etaMinutes}m with lower expected transfer friction.`,
    };
  }).sort((left, right) => (left.etaMinutes ?? Number.POSITIVE_INFINITY) - (right.etaMinutes ?? Number.POSITIVE_INFINITY)).slice(0, 5);

  const etaValues = plans
    .map((plan) => plan.etaMinutes)
    .filter((eta): eta is number => typeof eta === "number");

  const percentile = (values: readonly number[], p: number): number => {
    if (values.length === 0) {
      return 0;
    }
    const sorted = [...values].sort((left, right) => left - right);
    const index = Math.min(sorted.length - 1, Math.max(0, Math.floor((p / 100) * (sorted.length - 1))));
    return sorted[index] ?? 0;
  };

  const stdDev = (values: readonly number[]): number => {
    if (values.length <= 1) {
      return 0;
    }
    const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
    const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
    return Math.sqrt(variance);
  };

  const etaP50 = etaValues.length > 0 ? round(percentile(etaValues, 50), 1) : round(Math.max(8, horizonMinutes * 0.38), 1);
  const etaP90 = etaValues.length > 0 ? round(percentile(etaValues, 90), 1) : round(Math.max(15, horizonMinutes * 0.78), 1);
  const volatilityIndex = round(clamp((stdDev(etaValues) / Math.max(etaP50, 1)) * 100, 0, 100), 1);

  const disruptionPenalty = snapshot.trainAlerts.filter((alert) => Number(alert["status"]) === 2 || String(alert["status"]).toLowerCase() === "disrupted").length * 3.8;
  const incidentPenalty = snapshot.trafficIncidents.filter((incident) => getIncidentSeverity(String(incident["type"] ?? "")) === "high").length * 2.4;
  const roadPenalty = snapshot.roadEvents.length * 0.28;
  const missingEtaPenalty = plans.filter((plan) => plan.etaMinutes === null).length * 2.3;

  const reliabilityScore = round(clamp(100 - volatilityIndex * 0.46 - disruptionPenalty - incidentPenalty - roadPenalty - missingEtaPenalty, 5, 100), 1);
  const onTimeProbability = round(clamp(reliabilityScore / 100, 0.05, 0.99), 3);
  const confidence = round(clamp(0.35 + Math.min(0.4, etaValues.length * 0.08) + (originServices.length > 0 ? 0.1 : 0) + (destinationServices.length > 0 ? 0.06 : 0) - disruptionPenalty / 90, 0.15, 0.98), 3);

  return {
    generatedAt: toIsoNow(),
    input: {
      originStopId: params.originStopId,
      destinationStopId: params.destinationStopId,
      departureIso: toIsoNow(),
      horizonMinutes,
    },
    reliabilityScore,
    onTimeProbability,
    etaP50Minutes: etaP50,
    etaP90Minutes: etaP90,
    volatilityIndex,
    confidence,
    recommendedServicePlans: plans,
    explainers: [
      `Computed from ${plans.length} origin service candidates and ${etaValues.length} live ETA values.`,
      `${snapshot.trainAlerts.filter((alert) => Number(alert["status"]) === 2 || String(alert["status"]).toLowerCase() === "disrupted").length} disrupted rail alert(s) and ${snapshot.trafficIncidents.length} road incident(s) are active.`,
      `ETA spread estimates p50=${etaP50}m and p90=${etaP90}m.`,
    ],
  };
};

const buildTransferRisk = (
  snapshot: TransitSnapshot,
  params: Readonly<{ fromServiceNo: string; toServiceNo: string; transferStopId: string; expectedWalkMinutes?: number | undefined; minBufferMinutes?: number | undefined; fallbackServiceNos?: readonly string[] | undefined }>,
): Readonly<Record<string, unknown>> => {
  const services = snapshot.arrivalBoards[params.transferStopId] ?? [];
  const fromService = services.find((service) => String(service["serviceNo"] ?? "") === params.fromServiceNo);
  const toService = services.find((service) => String(service["serviceNo"] ?? "") === params.toServiceNo);
  const fromEta = fromService === undefined ? null : getBestEtaMinutes(fromService);
  const toEta = toService === undefined ? null : getBestEtaMinutes(toService);

  const expectedWalkMinutes = Math.max(1, params.expectedWalkMinutes ?? 4);
  const minBufferMinutes = Math.max(1, params.minBufferMinutes ?? 2);

  const highSeverityIncidentCount = snapshot.trafficIncidents.filter((incident) => getIncidentSeverity(String(incident["type"] ?? "")) === "high").length;
  const disruptedLineCount = snapshot.trainAlerts.filter((alert) => Number(alert["status"]) === 2 || String(alert["status"]).toLowerCase() === "disrupted").length;
  const contextPenalty = highSeverityIncidentCount * 0.06 + disruptedLineCount * 0.05;

  const fromArrivals = Array.isArray(fromService?.["arrivals"]) ? fromService?.["arrivals"] as readonly Readonly<Record<string, unknown>>[] : [];
  const fromLoad = typeof fromArrivals[0]?.["load"] === "string" ? String(fromArrivals[0]?.["load"]).trim().toUpperCase() : "";
  const fromLoadPenalty = fromLoad === "LSD" ? 0.08 : 0;

  let missProbability: number;
  if (fromEta === null || toEta === null) {
    missProbability = clamp(0.7 + contextPenalty, 0.45, 0.97);
  } else {
    const transferWindow = toEta - (fromEta + expectedWalkMinutes);
    const shortage = minBufferMinutes - transferWindow;
    missProbability = clamp(0.16 + shortage * 0.18 + contextPenalty + fromLoadPenalty, 0.03, 0.98);
  }

  const missRisk = missProbability >= 0.65 ? "high" : missProbability >= 0.35 ? "medium" : "low";

  const bufferMinutesRecommended = Math.max(minBufferMinutes, Math.round(minBufferMinutes + highSeverityIncidentCount * 0.7 + disruptedLineCount));

  const fallbackCandidates = params.fallbackServiceNos?.length
    ? [...params.fallbackServiceNos]
    : services
      .map((service) => String(service["serviceNo"] ?? ""))
      .filter((serviceNo) => serviceNo !== params.fromServiceNo && serviceNo !== params.toServiceNo)
      .slice(0, 4);

  const fallbackOptions = fallbackCandidates.map((serviceNo) => {
    const candidate = services.find((service) => String(service["serviceNo"] ?? "") === serviceNo);
    const etaMinutes = candidate === undefined ? null : getBestEtaMinutes(candidate);
    return {
      serviceNo,
      etaMinutes,
      rationale: etaMinutes === null ? "No live ETA available" : `Next vehicle in ${etaMinutes}m`,
    };
  });

  return {
    generatedAt: toIsoNow(),
    transferStopId: params.transferStopId,
    fromServiceNo: params.fromServiceNo,
    toServiceNo: params.toServiceNo,
    missRisk,
    missProbability: round(missProbability, 3),
    bufferMinutesRecommended,
    expectedWalkMinutes,
    fallbackOptions,
    explainers: [
      fromEta === null || toEta === null
        ? "Live ETA is incomplete for one or both services, so miss-risk is conservatively elevated."
        : `Estimated transfer window is ${round(toEta - (fromEta + expectedWalkMinutes), 1)} minute(s).`,
      `${highSeverityIncidentCount} high-severity road incident(s) and ${disruptedLineCount} disrupted line alert(s) are active.`,
    ],
  };
};

const buildAccessibleRoute = (
  snapshot: TransitSnapshot,
  params: Readonly<{ stopIds: readonly string[]; originLat: number; originLng: number; destinationLat: number; destinationLng: number; mobilityMode: TransitMobilityMode }>,
): Readonly<Record<string, unknown>> => {
  const stopIds = Array.from(new Set(params.stopIds));
  const origin = { lat: params.originLat, lng: params.originLng };
  const destination = { lat: params.destinationLat, lng: params.destinationLng };

  const routes: Array<Readonly<Record<string, unknown>>> = [];

  for (let index = 0; index < stopIds.length - 1; index += 1) {
    const fromStopId = stopIds[index]!;
    const toStopId = stopIds[index + 1]!;
    const fromLookup = snapshot.stopLookups[fromStopId];
    const toLookup = snapshot.stopLookups[toStopId];
    if (fromLookup?.lat === null || fromLookup?.lat === undefined || fromLookup?.lng === null || fromLookup?.lng === undefined) {
      continue;
    }
    if (toLookup?.lat === null || toLookup?.lat === undefined || toLookup?.lng === null || toLookup?.lng === undefined) {
      continue;
    }

    const fromServices = snapshot.arrivalBoards[fromStopId] ?? [];
    const bestService = fromServices
      .map((service) => ({
        serviceNo: String(service["serviceNo"] ?? "unknown"),
        etaMinutes: getBestEtaMinutes(service),
        service,
      }))
      .sort((left, right) => (left.etaMinutes ?? Number.POSITIVE_INFINITY) - (right.etaMinutes ?? Number.POSITIVE_INFINITY))[0];

    const walkToBoardMeters = haversineMeters(origin, { lat: fromLookup.lat, lng: fromLookup.lng });
    const walkFromAlightMeters = haversineMeters({ lat: toLookup.lat, lng: toLookup.lng }, destination);
    const walkMeters = walkToBoardMeters + walkFromAlightMeters;

    const arrivals = Array.isArray(bestService?.service["arrivals"]) ? bestService?.service["arrivals"] as readonly Readonly<Record<string, unknown>>[] : [];
    const load = typeof arrivals[0]?.["load"] === "string" ? String(arrivals[0]?.["load"]).trim().toUpperCase() : "";
    const crowdPenalty = load === "LSD" ? 18 : load === "SDA" ? 8 : 2;
    const etaMinutes = bestService?.etaMinutes ?? null;

    const accessibilityScore = round(clamp(
      100
        - walkMeters / (params.mobilityMode === "wheelchair" ? 16 : params.mobilityMode === "elder-friendly" ? 12 : 10)
        - crowdPenalty
        - (etaMinutes === null ? 20 : etaMinutes * 1.2),
      1,
      100,
    ), 1);

    const confidence = round(clamp(0.45 + (etaMinutes === null ? 0 : 0.25) - crowdPenalty / 100, 0.2, 0.95), 3);

    routes.push({
      id: `route-${fromStopId}-${toStopId}`,
      fromStopId,
      toStopId,
      serviceNo: bestService?.serviceNo ?? null,
      accessibilityScore,
      confidence,
      walkMeters: round(walkMeters, 1),
      transferCount: 1,
      crowdPenalty,
      liftRisk: load === "LSD" ? 0.55 : load === "SDA" ? 0.3 : 0.12,
      etaMinutes,
      wheelchairAccessible: load !== "LSD",
      rationale: `Board at ${fromLookup.name ?? fromStopId} and alight near ${toLookup.name ?? toStopId}.`,
    });
  }

  const sortedRoutes = routes.sort((left, right) => Number(right["accessibilityScore"]) - Number(left["accessibilityScore"]));

  return {
    generatedAt: toIsoNow(),
    mobilityMode: params.mobilityMode,
    origin,
    destination,
    recommendedRouteId: typeof sortedRoutes[0]?.["id"] === "string" ? sortedRoutes[0]!["id"] as string : undefined,
    routes: sortedRoutes,
  };
};

const applyPolicies = (
  candidates: readonly Readonly<{
    decision: TransitPlanDecision;
    confidence: number;
    walkMeters?: number;
    riskLevel: "low" | "medium" | "high";
    mobilityMode?: TransitMobilityMode;
    wheelchairAccessible?: boolean;
  }>[],
  profile: TransitTenantProfile,
  constraints: Readonly<Record<string, unknown>> | undefined,
): Readonly<{
  accepted: readonly TransitPlanDecision[];
  blocked: readonly TransitPolicyViolation[];
  evaluations: readonly TransitPolicyEvaluation[];
}> => {
  const minConfidence = clamp(
    typeof constraints?.["minConfidence"] === "number" ? Number(constraints["minConfidence"]) : profile.guardrails.minConfidence,
    0,
    1,
  );
  const maxWalkMeters = typeof constraints?.["maxWalkMeters"] === "number"
    ? Number(constraints["maxWalkMeters"])
    : profile.guardrails.maxWalkMeters;
  const avoidHighRisk = typeof constraints?.["avoidHighRisk"] === "boolean"
    ? Boolean(constraints["avoidHighRisk"])
    : profile.guardrails.avoidHighRisk;
  const requestedMobilityMode = typeof constraints?.["mobilityMode"] === "string"
    ? String(constraints["mobilityMode"])
    : undefined;

  const accepted: TransitPlanDecision[] = [];
  const blocked: TransitPolicyViolation[] = [];
  const evaluations: TransitPolicyEvaluation[] = [];

  for (const candidate of candidates) {
    if (candidate.confidence < minConfidence) {
      const reason = `${candidate.decision.id} blocked: confidence ${candidate.confidence.toFixed(2)} < ${minConfidence.toFixed(2)}`;
      blocked.push({ rule: "min-confidence", reason });
      evaluations.push({
        decisionId: candidate.decision.id,
        status: "blocked",
        rule: "min-confidence",
        reason,
        score: candidate.decision.score,
        confidence: candidate.confidence,
        riskLevel: candidate.riskLevel,
      });
      continue;
    }

    if (typeof candidate.walkMeters === "number" && candidate.walkMeters > maxWalkMeters) {
      const reason = `${candidate.decision.id} blocked: walk ${Math.round(candidate.walkMeters)}m > ${Math.round(maxWalkMeters)}m`;
      blocked.push({ rule: "max-walk-meters", reason });
      evaluations.push({
        decisionId: candidate.decision.id,
        status: "blocked",
        rule: "max-walk-meters",
        reason,
        score: candidate.decision.score,
        confidence: candidate.confidence,
        riskLevel: candidate.riskLevel,
      });
      continue;
    }

    if (avoidHighRisk && candidate.riskLevel === "high") {
      const reason = `${candidate.decision.id} blocked: risk level high`;
      blocked.push({ rule: "avoid-high-risk", reason });
      evaluations.push({
        decisionId: candidate.decision.id,
        status: "blocked",
        rule: "avoid-high-risk",
        reason,
        score: candidate.decision.score,
        confidence: candidate.confidence,
        riskLevel: candidate.riskLevel,
      });
      continue;
    }

    if (
      profile.guardrails.requireWheelchairAccessibleForMode
      && requestedMobilityMode === "wheelchair"
      && candidate.mobilityMode === "wheelchair"
      && candidate.wheelchairAccessible === false
    ) {
      const reason = `${candidate.decision.id} blocked: route lacks wheelchair accessibility signal`;
      blocked.push({ rule: "wheelchair-accessibility", reason });
      evaluations.push({
        decisionId: candidate.decision.id,
        status: "blocked",
        rule: "wheelchair-accessibility",
        reason,
        score: candidate.decision.score,
        confidence: candidate.confidence,
        riskLevel: candidate.riskLevel,
      });
      continue;
    }

    accepted.push(candidate.decision);
    evaluations.push({
      decisionId: candidate.decision.id,
      status: "accepted",
      rule: "accepted",
      reason: `${candidate.decision.id} accepted`,
      score: candidate.decision.score,
      confidence: candidate.confidence,
      riskLevel: candidate.riskLevel,
    });
  }

  return { accepted, blocked, evaluations };
};

const buildObjectivePlan = async (
  params: Readonly<{
    tenantId?: string | undefined;
    objective: TransitObjective;
    scopeKey?: string | undefined;
    stopIds?: readonly string[] | undefined;
    originStopId?: string | undefined;
    destinationStopId?: string | undefined;
    transferStopId?: string | undefined;
    fromServiceNo?: string | undefined;
    toServiceNo?: string | undefined;
    horizonMinutes?: number | undefined;
    maxActions?: number | undefined;
    constraints?: Readonly<Record<string, unknown>> | undefined;
  }>,
  options?: Readonly<{
    source?: "plan" | "counterfactual-baseline" | "counterfactual-scenario" | "policy-replay" | undefined;
    metadata?: Readonly<Record<string, unknown>> | undefined;
    updateMemory?: boolean | undefined;
  }>,
): Promise<Readonly<{ plan: TransitObjectivePlan; evaluations: readonly TransitPolicyEvaluation[]; traceId: string; snapshot: TransitSnapshot; health: TransitHealth; hotspots: TransitHotspots; briefing: TransitBriefing }>> => {
  const tenantProfile = getTenantProfile(params.tenantId);
  const tenantId = tenantProfile.tenantId;

  const stops = Array.from(new Set([
    ...(params.stopIds ?? []),
    ...(params.originStopId === undefined ? [] : [params.originStopId]),
    ...(params.destinationStopId === undefined ? [] : [params.destinationStopId]),
    ...(params.transferStopId === undefined ? [] : [params.transferStopId]),
  ])).filter((value) => /^\d{5}$/.test(value));

  const scopeKey = params.scopeKey?.trim() || (stops.length > 0 ? `plan:${stops.slice(0, 6).join(",")}` : DEFAULT_SCOPE_KEY);

  const snapshot = await buildSnapshot({ stopIds: stops, includeTrafficImages: true });
  const health = buildHealth(snapshot);
  const hotspots = buildHotspots(snapshot);
  const briefing = buildOpsBriefing(health, hotspots, scopeKey);

  const explainers: string[] = [];
  const candidates: Array<Readonly<{
    decision: TransitPlanDecision;
    confidence: number;
    walkMeters?: number;
    riskLevel: "low" | "medium" | "high";
    mobilityMode?: TransitMobilityMode;
    wheelchairAccessible?: boolean;
  }>> = [];

  if (params.originStopId !== undefined && params.destinationStopId !== undefined) {
    const reliability = buildReliability(snapshot, {
      originStopId: params.originStopId,
      destinationStopId: params.destinationStopId,
      horizonMinutes: params.horizonMinutes,
    });

    const plans = Array.isArray(reliability["recommendedServicePlans"]) ? reliability["recommendedServicePlans"] as readonly Readonly<Record<string, unknown>>[] : [];
    for (const plan of plans.slice(0, 4)) {
      const etaMinutes = typeof plan["etaMinutes"] === "number" ? Number(plan["etaMinutes"]) : null;
      const confidence = typeof plan["confidence"] === "number" ? Number(plan["confidence"]) : 0.3;
      const score = round(clamp(
        Number(reliability["reliabilityScore"]) * tenantProfile.weights.reliability
          - (etaMinutes === null ? 10 : etaMinutes),
        1,
        100,
      ), 1);

      const decision: TransitPlanDecision = {
        id: `reliability-${String(plan["serviceNo"] ?? randomUUID())}`,
        score,
        confidence,
        title: `Prioritize service ${String(plan["serviceNo"] ?? "unknown")}`,
        detail: String(plan["rationale"] ?? "Reliability candidate based on current ETA distribution."),
        actions: [
          {
            type: "recommend_route",
            title: "Recommend route",
            detail: `Use service ${String(plan["serviceNo"] ?? "unknown")} with ETA ${etaMinutes ?? "unknown"} minutes.`,
            relatedStopId: params.originStopId,
          },
        ],
        references: [{ type: "reliability", id: String(plan["serviceNo"] ?? "unknown") }],
      };

      candidates.push({
        decision,
        confidence,
        riskLevel: toRiskLevel(score),
      });
    }
    explainers.push("Reliability candidates generated from live ETA dispersion and disruption context.");
  }

  if (
    params.transferStopId !== undefined
    && params.fromServiceNo !== undefined
    && params.toServiceNo !== undefined
  ) {
    const transfer = buildTransferRisk(snapshot, {
      transferStopId: params.transferStopId,
      fromServiceNo: params.fromServiceNo,
      toServiceNo: params.toServiceNo,
    });
    const missProbability = typeof transfer["missProbability"] === "number" ? Number(transfer["missProbability"]) : 0.5;
    const confidence = round(clamp(1 - missProbability, 0.1, 0.95), 3);
    const score = round(clamp((1 - missProbability) * 100 * tenantProfile.weights.transferRisk, 1, 100), 1);

    const decision: TransitPlanDecision = {
      id: `transfer-${params.fromServiceNo}-${params.toServiceNo}`,
      score,
      confidence,
      title: `Manage transfer ${params.fromServiceNo} -> ${params.toServiceNo}`,
      detail: `Miss probability ${round(missProbability * 100, 1)}%; recommended buffer ${String(transfer["bufferMinutesRecommended"] ?? "n/a")} minutes.`,
      actions: [
        {
          type: "recommend_transfer_buffer",
          title: "Recommend transfer buffer",
          detail: `Keep at least ${String(transfer["bufferMinutesRecommended"] ?? "n/a")} minutes transfer buffer.`,
          relatedStopId: params.transferStopId,
        },
      ],
      references: [{ type: "transfer-risk", id: `${params.transferStopId}:${params.fromServiceNo}:${params.toServiceNo}` }],
    };

    candidates.push({
      decision,
      confidence,
      riskLevel: transfer["missRisk"] === "high" ? "high" : transfer["missRisk"] === "medium" ? "medium" : "low",
    });
    explainers.push("Transfer-risk candidate generated from ETA alignment and live incident context.");
  }

  const severeHotspot = hotspots.hotspots[0];
  if (severeHotspot !== undefined) {
    const score = round(clamp(100 - Number(severeHotspot.riskScore), 1, 100), 1);
    const confidence = round(clamp(0.45 + (severeHotspot.level === "severe" ? 0.35 : 0.2), 0.2, 0.95), 3);
    candidates.push({
      decision: {
        id: `ops-${String(severeHotspot.hotspotId)}`,
        score: round(clamp(score * tenantProfile.weights.operations, 1, 100), 1),
        confidence,
        title: `Ops mitigation for ${String(severeHotspot.hotspotId)}`,
        detail: `${String(severeHotspot.highlights?.join("; ") ?? "Operational hotspot detected")}.`,
        actions: [
          {
            type: "escalate_ops",
            title: "Escalate operations",
            detail: `Escalate hotspot ${String(severeHotspot.hotspotId)} with risk score ${String(severeHotspot.riskScore)}.`,
          },
        ],
        references: [{ type: "hotspot", id: String(severeHotspot.hotspotId) }],
      },
      confidence,
      riskLevel: severeHotspot.level === "severe" ? "high" : severeHotspot.level === "high" ? "medium" : "low",
    });
  }

  const worstStop = health.stops[0];
  if (worstStop !== undefined) {
    const stopScore = typeof worstStop["score"] === "number" ? Number(worstStop["score"]) : 30;
    const confidence = round(clamp(0.45 + (100 - stopScore) / 200, 0.2, 0.92), 3);
    candidates.push({
      decision: {
        id: `health-${String(worstStop["stopId"] ?? randomUUID())}`,
        score: round(clamp((100 - stopScore) * tenantProfile.weights.operations, 1, 100), 1),
        confidence,
        title: `Monitor stop ${String(worstStop["stopId"] ?? "unknown")}`,
        detail: `Stop health score ${String(worstStop["score"] ?? "n/a")}; prioritize rider messaging and monitoring.`,
        actions: [
          {
            type: "inform_user",
            title: "Inform commuters",
            detail: `Broadcast elevated wait risk at stop ${String(worstStop["stopId"] ?? "unknown")}.`,
            relatedStopId: worstStop["stopId"],
          },
        ],
        references: [{ type: "health", id: String(worstStop["stopId"] ?? "unknown") }],
      },
      confidence,
      riskLevel: toRiskLevel(stopScore),
    });
  }

  if (candidates.length === 0) {
    explainers.push("No decision candidates could be generated from the provided inputs.");
  }

  const filtered = applyPolicies(candidates, tenantProfile, params.constraints);
  const maxActions = Math.max(1, params.maxActions ?? 5);
  const accepted = [...filtered.accepted].sort((left, right) => right.score - left.score).slice(0, maxActions);

  const plan: TransitObjectivePlan = {
    generatedAt: toIsoNow(),
    tenantId,
    scopeKey,
    objective: params.objective,
    riskIndex: briefing.riskIndex,
    trend: briefing.trend,
    decisions: accepted,
    blockedByPolicies: filtered.blocked,
    explainers,
  };

  if (options?.updateMemory !== false) {
    upsertTenantMemory(tenantId, scopeKey, plan.riskIndex, plan.trend, plan.decisions.map((decision) => decision.id));
  }

  const traceId = randomUUID();
  const auditRecord: TransitPolicyAuditRecord = {
    traceId,
    timestamp: toIsoNow(),
    tenantId,
    scopeKey,
    source: options?.source ?? "plan",
    objective: plan.objective,
    riskIndex: plan.riskIndex,
    trend: plan.trend,
    request: {
      objective: params.objective,
      scopeKey: params.scopeKey,
      stopIds: params.stopIds,
      originStopId: params.originStopId,
      destinationStopId: params.destinationStopId,
      transferStopId: params.transferStopId,
      fromServiceNo: params.fromServiceNo,
      toServiceNo: params.toServiceNo,
      horizonMinutes: params.horizonMinutes,
      maxActions: params.maxActions,
      constraints: params.constraints,
    },
    guardrails: tenantProfile.guardrails,
    thresholds: tenantProfile.thresholds,
    weights: tenantProfile.weights,
    policyEvaluations: filtered.evaluations,
    acceptedDecisionIds: accepted.map((decision) => decision.id),
    blockedByPolicies: filtered.blocked,
    ...(options?.metadata === undefined ? {} : { metadata: options.metadata }),
  };
  policyAuditRecords.push(auditRecord);

  return {
    plan,
    evaluations: filtered.evaluations,
    traceId,
    snapshot,
    health,
    hotspots,
    briefing,
  };
};

const computeModelMetrics = (scopeKey: string | undefined): Readonly<Record<string, unknown>> => {
  const filtered = scopeKey === undefined
    ? outcomeEvents
    : outcomeEvents.filter((event) => event.scopeKey === scopeKey);

  const mean = (values: readonly number[]): number | null => {
    if (values.length === 0) {
      return null;
    }
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  };

  const acceptedCount = filtered.filter((event) => event.accepted).length;
  const successCount = filtered.filter((event) => event.success === true).length;

  const predictionErrors = filtered
    .map((event) => {
      if (typeof event.predictedWaitMinutes !== "number" || typeof event.actualWaitMinutes !== "number") {
        return null;
      }
      return Math.abs(event.predictedWaitMinutes - event.actualWaitMinutes);
    })
    .filter((value): value is number => value !== null);

  const calibrationErrors = filtered
    .map((event) => {
      if (typeof event.confidence !== "number" || typeof event.success !== "boolean") {
        return null;
      }
      const target = event.success ? 1 : 0;
      return Math.abs(event.confidence - target);
    })
    .filter((value): value is number => value !== null);

  const riskErrors = filtered
    .map((event) => {
      if (typeof event.predictedRisk !== "number" || typeof event.actualRisk !== "number") {
        return null;
      }
      return Math.abs(event.predictedRisk - event.actualRisk);
    })
    .filter((value): value is number => value !== null);

  const recommendationTypes: readonly TransitOutcomeEvent["recommendationType"][] = [
    "reliability",
    "transfer-risk",
    "playbook",
    "accessibility",
  ];

  const byRecommendationType: Record<string, Readonly<Record<string, unknown>>> = {};
  for (const type of recommendationTypes) {
    const events = filtered.filter((event) => event.recommendationType === type);
    const typeAccepted = events.filter((event) => event.accepted).length;
    const typeSuccess = events.filter((event) => event.success === true).length;
    byRecommendationType[type] = {
      eventCount: events.length,
      acceptedCount: typeAccepted,
      successRate: events.length === 0 ? 0 : round(typeSuccess / events.length, 4),
    };
  }

  return {
    generatedAt: toIsoNow(),
    totals: {
      eventCount: filtered.length,
      acceptedCount,
      successCount,
      successRate: filtered.length === 0 ? 0 : round(successCount / filtered.length, 4),
    },
    quality: {
      predictionErrorMinutes: predictionErrors.length === 0 ? null : round(mean(predictionErrors) ?? 0, 3),
      calibrationError: calibrationErrors.length === 0 ? null : round(mean(calibrationErrors) ?? 0, 4),
      riskError: riskErrors.length === 0 ? null : round(mean(riskErrors) ?? 0, 4),
    },
    byRecommendationType,
  };
};

const computePolicyInsights = (
  records: readonly TransitPolicyAuditRecord[],
): Readonly<Record<string, unknown>> => {
  const evaluations = records.flatMap((record) => record.policyEvaluations);
  const blocked = evaluations.filter((entry) => entry.status === "blocked");
  const accepted = evaluations.filter((entry) => entry.status === "accepted");

  const ruleCounts = blocked.reduce<Record<string, number>>((accumulator, entry) => {
    accumulator[entry.rule] = (accumulator[entry.rule] ?? 0) + 1;
    return accumulator;
  }, {});

  return {
    generatedAt: toIsoNow(),
    window: {
      count: records.length,
      tenantId: records[0]?.tenantId,
      scopeKey: records[0]?.scopeKey,
    },
    totals: {
      accepted: accepted.length,
      blocked: blocked.length,
      acceptanceRate: evaluations.length === 0 ? 0 : round(accepted.length / evaluations.length, 4),
    },
    topBlockingRules: Object.entries(ruleCounts)
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5)
      .map(([rule, count]) => ({ rule, count })),
    highRiskTraces: records.filter((record) => record.riskIndex >= Number(record.thresholds["highRiskIndex"] ?? 60)).length,
  };
};

const toToolResult = (payload: unknown, format: OutputFormat): ToolResult => ({
  content: [{ type: "text", text: format === "markdown" ? formatResponse(payload as Record<string, unknown>, "markdown") : formatResponse(payload as Record<string, unknown>, "json") }],
  structuredContent: { record: payload as Readonly<Record<string, unknown>> },
});

const toBriefToolResult = (payload: BriefArtifact, format: OutputFormat): ToolResult => {
  const validated = BriefArtifactSchema.parse(payload) as BriefArtifact;
  return {
    content: [{ type: "text", text: format === "markdown" ? formatResponse(validated as unknown as Record<string, unknown>, "markdown") : formatResponse(validated as unknown as Record<string, unknown>, "json") }],
    structuredContent: { record: validated },
  };
};

export const handleTransitHealth = async (
  params: Readonly<{ stopIds?: readonly string[] | undefined; includeTrafficImages?: boolean | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const snapshot = await buildSnapshot(params);
  const health = buildHealth(snapshot);
  const format = resolveOutputFormat(params.format);
  return toToolResult(health, format === "markdown" ? "markdown" : "json");
};

export const handleTransitHotspots = async (
  params: Readonly<{ stopIds?: readonly string[] | undefined; includeTrafficImages?: boolean | undefined; gridSizeDegrees?: number | undefined; impactRadiusMeters?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const snapshot = await buildSnapshot(params);
  const hotspots = buildHotspots(snapshot, {
    gridSizeDegrees: params.gridSizeDegrees,
    impactRadiusMeters: params.impactRadiusMeters,
  });
  const format = resolveOutputFormat(params.format);
  return toToolResult(hotspots, format === "markdown" ? "markdown" : "json");
};

export const handleTransitOpsBrief = async (
  params: Readonly<{ stopIds?: readonly string[] | undefined; scopeKey?: string | undefined; includeTrafficImages?: boolean | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const pack = await buildPack(params);

  const payload: BriefArtifact = {
    title: "Transit Ops Brief",
    summary: [
      { label: "Headline", value: pack.briefing.headline, source: "Transit intelligence" },
      { label: "Trend", value: pack.briefing.trend, source: "Transit intelligence" },
      { label: "Risk index", value: pack.briefing.riskIndex, source: "Transit intelligence" },
    ],
    evidence: [
      { label: "Watched stops", value: pack.health.summary.stopCount, source: "LTA" },
      { label: "Critical stops", value: pack.health.summary.criticalStopCount, source: "LTA" },
      { label: "Hotspots", value: pack.hotspots.summary.hotspotCount, source: "LTA + data.gov.sg" },
      { label: "Severe hotspots", value: pack.hotspots.summary.severeHotspotCount, source: "LTA + data.gov.sg" },
    ],
    records: {
      briefing: pack.briefing,
      health: pack.health,
      hotspots: pack.hotspots,
      snapshot: {
        generatedAt: pack.snapshot.generatedAt,
        stopIds: pack.snapshot.stopIds,
      },
    },
    gaps: [],
    provenance: [
      {
        source: "LTA DataMall",
        tool: "sg_lta_bus_arrivals",
        coverage: "Live stop-level bus arrivals for the provided watch stops.",
        authRequired: true,
        recordCount: pack.health.summary.serviceCount,
      },
      {
        source: "LTA DataMall",
        tool: "sg_lta_train_alerts",
        coverage: "Network-wide train alerts and operator messages.",
        authRequired: true,
        recordCount: pack.snapshot.trainAlerts.length + pack.snapshot.trainMessages.length,
      },
      {
        source: "LTA DataMall",
        tool: "sg_lta_traffic_incidents",
        coverage: "Live traffic incidents and road-event overlays.",
        authRequired: true,
        recordCount: pack.snapshot.trafficIncidents.length + pack.snapshot.roadEvents.length,
      },
      {
        source: "data.gov.sg",
        tool: "sg_lta_traffic_images",
        coverage: "Traffic camera image references and camera coordinates.",
        authRequired: false,
        recordCount: pack.snapshot.trafficImages.length,
      },
    ],
    freshness: [
      {
        source: "Transit intelligence",
        observedAt: pack.generatedAt,
        upstreamTimestamp: pack.generatedAt,
      },
    ],
    limits: [
      {
        code: "NOT_A_ROUTER",
        message: "This brief is a bounded operational snapshot and does not replace route planning or dispatch optimization systems.",
      },
      {
        code: "HEURISTIC_SCORING",
        message: "Risk and hotspot scores are deterministic heuristics over public feeds, not predictive guarantees.",
      },
    ],
    nextChecks: [
      {
        tool: "sg_transit_pack",
        reason: "Retrieve full snapshot, health, hotspots, and briefing in one payload.",
        input: {
          ...(params.stopIds === undefined ? {} : { stopIds: params.stopIds }),
          ...(params.scopeKey === undefined ? {} : { scopeKey: params.scopeKey }),
        },
      },
      {
        tool: "sg_transit_objective_plan",
        reason: "Generate policy-aware objective decisions from the current operational context.",
        input: {
          objective: "balanced",
          ...(params.scopeKey === undefined ? {} : { scopeKey: params.scopeKey }),
          ...(params.stopIds === undefined ? {} : { stopIds: params.stopIds }),
        },
      },
    ],
  };

  const format = resolveOutputFormat(params.format);
  return toBriefToolResult(payload, format === "markdown" ? "markdown" : "json");
};

export const handleTransitPack = async (
  params: Readonly<{ stopIds?: readonly string[] | undefined; scopeKey?: string | undefined; includeTrafficImages?: boolean | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const pack = await buildPack(params);
  const format = resolveOutputFormat(params.format);
  return toToolResult(pack, format === "markdown" ? "markdown" : "json");
};

export const handleTransitReliability = async (
  params: Readonly<{ originStopId: string; destinationStopId: string; horizonMinutes?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const snapshot = await buildSnapshot({ stopIds: [params.originStopId, params.destinationStopId], includeTrafficImages: false });
  const payload = buildReliability(snapshot, params);
  const format = resolveOutputFormat(params.format);
  return toToolResult(payload, format === "markdown" ? "markdown" : "json");
};

export const handleTransitTransferRisk = async (
  params: Readonly<{ fromServiceNo: string; toServiceNo: string; transferStopId: string; expectedWalkMinutes?: number | undefined; minBufferMinutes?: number | undefined; fallbackServiceNos?: readonly string[] | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const snapshot = await buildSnapshot({ stopIds: [params.transferStopId], includeTrafficImages: false });
  const payload = buildTransferRisk(snapshot, params);
  const format = resolveOutputFormat(params.format);
  return toToolResult(payload, format === "markdown" ? "markdown" : "json");
};

export const handleTransitAccessibleRoute = async (
  params: Readonly<{ stopIds: readonly string[]; originLat: number; originLng: number; destinationLat: number; destinationLng: number; mobilityMode: TransitMobilityMode; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const snapshot = await buildSnapshot({ stopIds: params.stopIds, includeTrafficImages: false });
  const payload = buildAccessibleRoute(snapshot, params);
  const format = resolveOutputFormat(params.format);
  return toToolResult(payload, format === "markdown" ? "markdown" : "json");
};

export const handleTransitObjectivePlan = async (
  params: Readonly<{ tenantId?: string | undefined; objective: TransitObjective; scopeKey?: string | undefined; stopIds?: readonly string[] | undefined; originStopId?: string | undefined; destinationStopId?: string | undefined; transferStopId?: string | undefined; fromServiceNo?: string | undefined; toServiceNo?: string | undefined; horizonMinutes?: number | undefined; maxActions?: number | undefined; constraints?: Readonly<Record<string, unknown>> | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const payload = await buildObjectivePlan(params, {
    source: "plan",
    updateMemory: true,
  });
  const format = resolveOutputFormat(params.format);
  return toToolResult({
    traceId: payload.traceId,
    plan: payload.plan,
    evaluations: payload.evaluations,
    memory: getTenantMemory(payload.plan.tenantId, payload.plan.scopeKey),
  }, format === "markdown" ? "markdown" : "json");
};

export const handleTransitCounterfactualSimulate = async (
  params: Readonly<{ tenantId?: string | undefined; baseRequest: Readonly<Record<string, unknown>>; scenarios: readonly Readonly<Record<string, unknown>>[]; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const baseRequest = params.baseRequest;
  const tenantId = typeof params.tenantId === "string" ? params.tenantId : undefined;

  const baseline = await buildObjectivePlan({
    tenantId,
    objective: String(baseRequest["objective"] ?? "balanced") as TransitObjective,
    scopeKey: typeof baseRequest["scopeKey"] === "string" ? String(baseRequest["scopeKey"]) : undefined,
    stopIds: Array.isArray(baseRequest["stopIds"]) ? baseRequest["stopIds"] as readonly string[] : undefined,
    originStopId: typeof baseRequest["originStopId"] === "string" ? String(baseRequest["originStopId"]) : undefined,
    destinationStopId: typeof baseRequest["destinationStopId"] === "string" ? String(baseRequest["destinationStopId"]) : undefined,
    transferStopId: typeof baseRequest["transferStopId"] === "string" ? String(baseRequest["transferStopId"]) : undefined,
    fromServiceNo: typeof baseRequest["fromServiceNo"] === "string" ? String(baseRequest["fromServiceNo"]) : undefined,
    toServiceNo: typeof baseRequest["toServiceNo"] === "string" ? String(baseRequest["toServiceNo"]) : undefined,
    horizonMinutes: typeof baseRequest["horizonMinutes"] === "number" ? Number(baseRequest["horizonMinutes"]) : undefined,
    maxActions: typeof baseRequest["maxActions"] === "number" ? Number(baseRequest["maxActions"]) : undefined,
    constraints: typeof baseRequest["constraints"] === "object" && baseRequest["constraints"] !== null ? baseRequest["constraints"] as Readonly<Record<string, unknown>> : undefined,
  }, {
    source: "counterfactual-baseline",
    metadata: { simulation: true },
    updateMemory: false,
  });

  const scenarioResults = [];
  for (const [index, scenario] of params.scenarios.entries()) {
    const requestPatch = typeof scenario["requestPatch"] === "object" && scenario["requestPatch"] !== null
      ? scenario["requestPatch"] as Readonly<Record<string, unknown>>
      : {};
    const constraintsPatch = typeof scenario["constraintsPatch"] === "object" && scenario["constraintsPatch"] !== null
      ? scenario["constraintsPatch"] as Readonly<Record<string, unknown>>
      : undefined;

    const mergedBaseConstraints = typeof baseRequest["constraints"] === "object" && baseRequest["constraints"] !== null
      ? baseRequest["constraints"] as Readonly<Record<string, unknown>>
      : undefined;

    const scenarioPlan = await buildObjectivePlan({
      tenantId,
      objective: String(requestPatch["objective"] ?? baseRequest["objective"] ?? "balanced") as TransitObjective,
      scopeKey: typeof requestPatch["scopeKey"] === "string"
        ? String(requestPatch["scopeKey"])
        : typeof baseRequest["scopeKey"] === "string"
          ? String(baseRequest["scopeKey"])
          : undefined,
      stopIds: Array.isArray(requestPatch["stopIds"])
        ? requestPatch["stopIds"] as readonly string[]
        : Array.isArray(baseRequest["stopIds"])
          ? baseRequest["stopIds"] as readonly string[]
          : undefined,
      originStopId: typeof requestPatch["originStopId"] === "string"
        ? String(requestPatch["originStopId"])
        : typeof baseRequest["originStopId"] === "string"
          ? String(baseRequest["originStopId"])
          : undefined,
      destinationStopId: typeof requestPatch["destinationStopId"] === "string"
        ? String(requestPatch["destinationStopId"])
        : typeof baseRequest["destinationStopId"] === "string"
          ? String(baseRequest["destinationStopId"])
          : undefined,
      transferStopId: typeof requestPatch["transferStopId"] === "string"
        ? String(requestPatch["transferStopId"])
        : typeof baseRequest["transferStopId"] === "string"
          ? String(baseRequest["transferStopId"])
          : undefined,
      fromServiceNo: typeof requestPatch["fromServiceNo"] === "string"
        ? String(requestPatch["fromServiceNo"])
        : typeof baseRequest["fromServiceNo"] === "string"
          ? String(baseRequest["fromServiceNo"])
          : undefined,
      toServiceNo: typeof requestPatch["toServiceNo"] === "string"
        ? String(requestPatch["toServiceNo"])
        : typeof baseRequest["toServiceNo"] === "string"
          ? String(baseRequest["toServiceNo"])
          : undefined,
      horizonMinutes: typeof requestPatch["horizonMinutes"] === "number"
        ? Number(requestPatch["horizonMinutes"])
        : typeof baseRequest["horizonMinutes"] === "number"
          ? Number(baseRequest["horizonMinutes"])
          : undefined,
      maxActions: typeof scenario["maxActions"] === "number"
        ? Number(scenario["maxActions"])
        : typeof requestPatch["maxActions"] === "number"
          ? Number(requestPatch["maxActions"])
          : typeof baseRequest["maxActions"] === "number"
            ? Number(baseRequest["maxActions"])
            : undefined,
      constraints: {
        ...(mergedBaseConstraints ?? {}),
        ...(typeof requestPatch["constraints"] === "object" && requestPatch["constraints"] !== null ? requestPatch["constraints"] as Readonly<Record<string, unknown>> : {}),
        ...(constraintsPatch ?? {}),
      },
    }, {
      source: "counterfactual-scenario",
      metadata: {
        scenarioId: typeof scenario["id"] === "string" ? scenario["id"] : `scenario-${index + 1}`,
        label: typeof scenario["label"] === "string" ? scenario["label"] : `Scenario ${index + 1}`,
      },
      updateMemory: false,
    });

    scenarioResults.push({
      scenarioId: typeof scenario["id"] === "string" ? scenario["id"] : `scenario-${index + 1}`,
      label: typeof scenario["label"] === "string" ? scenario["label"] : `Scenario ${index + 1}`,
      traceId: scenarioPlan.traceId,
      plan: scenarioPlan.plan,
      delta: {
        riskIndex: round(scenarioPlan.plan.riskIndex - baseline.plan.riskIndex, 1),
        decisionCount: scenarioPlan.plan.decisions.length - baseline.plan.decisions.length,
        blockedCount: scenarioPlan.plan.blockedByPolicies.length - baseline.plan.blockedByPolicies.length,
        topDecisionScore: round((scenarioPlan.plan.decisions[0]?.score ?? 0) - (baseline.plan.decisions[0]?.score ?? 0), 1),
      },
    });
  }

  const scored = scenarioResults
    .map((scenario) => ({
      scenarioId: scenario.scenarioId,
      score: (scenario.plan.decisions[0]?.score ?? 0) + scenario.plan.decisions.length * 4 - scenario.plan.blockedByPolicies.length * 6 - scenario.plan.riskIndex * 0.08,
    }))
    .sort((left, right) => right.score - left.score);

  const format = resolveOutputFormat(params.format);
  return toToolResult({
    generatedAt: toIsoNow(),
    tenantId: baseline.plan.tenantId,
    scopeKey: baseline.plan.scopeKey,
    baselineTraceId: baseline.traceId,
    baseline: baseline.plan,
    scenarios: scenarioResults,
    recommendedScenarioId: scored[0]?.scenarioId,
    recommendationRationale: scored.length === 0
      ? "No scenarios supplied."
      : "Recommended by weighted comparison of top decision score, accepted decisions, blocked policies, and risk index.",
  }, format === "markdown" ? "markdown" : "json");
};

export const handleTransitOutcomeRecord = async (
  params: Readonly<{
    scopeKey?: string | undefined;
    recommendationType: TransitOutcomeEvent["recommendationType"];
    recommendationId?: string | undefined;
    accepted: boolean;
    success?: boolean | undefined;
    confidence?: number | undefined;
    predictedWaitMinutes?: number | undefined;
    actualWaitMinutes?: number | undefined;
    predictedRisk?: number | undefined;
    actualRisk?: number | undefined;
    metadata?: Readonly<Record<string, unknown>> | undefined;
  }>,
): Promise<ToolResult> => {
  const event: TransitOutcomeEvent = {
    id: randomUUID(),
    timestamp: toIsoNow(),
    recommendationType: params.recommendationType,
    accepted: params.accepted,
    ...(params.scopeKey === undefined ? {} : { scopeKey: params.scopeKey }),
    ...(params.recommendationId === undefined ? {} : { recommendationId: params.recommendationId }),
    ...(params.success === undefined ? {} : { success: params.success }),
    ...(params.confidence === undefined ? {} : { confidence: params.confidence }),
    ...(params.predictedWaitMinutes === undefined ? {} : { predictedWaitMinutes: params.predictedWaitMinutes }),
    ...(params.actualWaitMinutes === undefined ? {} : { actualWaitMinutes: params.actualWaitMinutes }),
    ...(params.predictedRisk === undefined ? {} : { predictedRisk: params.predictedRisk }),
    ...(params.actualRisk === undefined ? {} : { actualRisk: params.actualRisk }),
    ...(params.metadata === undefined ? {} : { metadata: params.metadata }),
  };
  outcomeEvents.push(event);
  return {
    content: [{ type: "text", text: formatResponse(event as unknown as Record<string, unknown>, "json") }],
    structuredContent: {
      record: event as unknown as Readonly<Record<string, unknown>>,
    },
  };
};

export const handleTransitModelMetrics = async (
  params: Readonly<{ scopeKey?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const metrics = computeModelMetrics(params.scopeKey);
  const format = resolveOutputFormat(params.format);
  return toToolResult(metrics, format === "markdown" ? "markdown" : "json");
};

export const handleTransitPolicyAudit = async (
  params: Readonly<{ tenantId?: string | undefined; scopeKey?: string | undefined; source?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const limit = Math.max(1, Math.min(500, params.limit ?? 100));
  const records = policyAuditRecords
    .filter((record) => params.tenantId === undefined || record.tenantId === params.tenantId)
    .filter((record) => params.scopeKey === undefined || record.scopeKey === params.scopeKey)
    .filter((record) => params.source === undefined || record.source === params.source)
    .sort((left, right) => right.timestamp.localeCompare(left.timestamp))
    .slice(0, limit);
  const format = resolveOutputFormat(params.format);
  return toToolResult({ records }, format === "markdown" ? "markdown" : "json");
};

export const handleTransitPolicyInsights = async (
  params: Readonly<{ tenantId?: string | undefined; scopeKey?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const records = policyAuditRecords
    .filter((record) => params.tenantId === undefined || record.tenantId === params.tenantId)
    .filter((record) => params.scopeKey === undefined || record.scopeKey === params.scopeKey)
    .sort((left, right) => right.timestamp.localeCompare(left.timestamp))
    .slice(0, 500);
  const insights = computePolicyInsights(records);
  const format = resolveOutputFormat(params.format);
  return toToolResult(insights, format === "markdown" ? "markdown" : "json");
};

export const handleTransitPolicyReplay = async (
  params: Readonly<{ traceId: string; constraintsPatch?: Readonly<Record<string, unknown>> | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const requestId = randomUUID();
  const record = policyAuditRecords.find((entry) => entry.traceId === params.traceId);
  if (record === undefined) {
    return {
      isError: true,
      content: [{ type: "text", text: `No policy audit trace found for traceId ${params.traceId}.` }],
      structuredContent: {
        error: {
          source: "sg_transit_policy_replay",
          tool: "sg_transit_policy_replay",
          code: "TRANSIT_TRACE_NOT_FOUND",
          retryable: false,
          severity: "low",
          category: "workflow_dependency",
          message: `No policy audit trace found for traceId ${params.traceId}.`,
          suggestedAction: "Call sg_transit_policy_audit first and pass a valid traceId.",
          statusCode: 404,
          contextIds: {
            traceId: requestId,
            requestId,
          },
        },
      },
    };
  }

  const request = record.request;
  const replay = await buildObjectivePlan({
    tenantId: record.tenantId,
    objective: String(request["objective"] ?? "balanced") as TransitObjective,
    scopeKey: typeof request["scopeKey"] === "string" ? String(request["scopeKey"]) : record.scopeKey,
    stopIds: Array.isArray(request["stopIds"]) ? request["stopIds"] as readonly string[] : undefined,
    originStopId: typeof request["originStopId"] === "string" ? String(request["originStopId"]) : undefined,
    destinationStopId: typeof request["destinationStopId"] === "string" ? String(request["destinationStopId"]) : undefined,
    transferStopId: typeof request["transferStopId"] === "string" ? String(request["transferStopId"]) : undefined,
    fromServiceNo: typeof request["fromServiceNo"] === "string" ? String(request["fromServiceNo"]) : undefined,
    toServiceNo: typeof request["toServiceNo"] === "string" ? String(request["toServiceNo"]) : undefined,
    horizonMinutes: typeof request["horizonMinutes"] === "number" ? Number(request["horizonMinutes"]) : undefined,
    maxActions: typeof request["maxActions"] === "number" ? Number(request["maxActions"]) : undefined,
    constraints: {
      ...(typeof request["constraints"] === "object" && request["constraints"] !== null ? request["constraints"] as Readonly<Record<string, unknown>> : {}),
      ...(params.constraintsPatch ?? {}),
    },
  }, {
    source: "policy-replay",
    metadata: { parentTraceId: record.traceId },
    updateMemory: false,
  });

  const format = resolveOutputFormat(params.format);
  return toToolResult({
    parentTraceId: record.traceId,
    replayTraceId: replay.traceId,
    plan: replay.plan,
    evaluations: replay.evaluations,
  }, format === "markdown" ? "markdown" : "json");
};

export const transitIntelligenceToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_transit_health",
    description: "Score watched bus stops and services with deterministic transit-health grades and risk drivers.",
    surface: "canonical",
    positioning: "Transit intelligence primitive over live LTA operational feeds.",
    toolsets: ["public", "property"],
    inputSchema: TransitHealthSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitHealth(validateInput(TransitHealthSchema, input)),
  },
  {
    name: "sg_transit_hotspots",
    description: "Cluster incidents, road events, and traffic camera context into impact-ranked transit hotspots.",
    surface: "canonical",
    positioning: "Transit intelligence primitive for geospatial incident triage.",
    toolsets: ["public", "property"],
    inputSchema: TransitHotspotsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitHotspots(validateInput(TransitHotspotsSchema, input)),
  },
  {
    name: "sg_transit_ops_brief",
    description: "Build a bounded transit-operations brief combining health, hotspots, and trend-aware action priorities.",
    surface: "canonical",
    positioning: "High-value additive brief for transit operations over direct transport feeds.",
    toolsets: ["briefs", "property"],
    inputSchema: TransitOpsBriefSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitOpsBrief(validateInput(TransitOpsBriefSchema, input)),
  },
  {
    name: "sg_transit_pack",
    description: "Return one transit intelligence payload with snapshot, health, hotspots, and ops briefing.",
    surface: "canonical",
    positioning: "Primary integration payload for transit-intelligence clients.",
    toolsets: ["public", "property"],
    inputSchema: TransitPackSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitPack(validateInput(TransitPackSchema, input)),
  },
  {
    name: "sg_transit_reliability",
    description: "Estimate origin-destination transit reliability with ETA bands, volatility, and candidate service plans.",
    surface: "canonical",
    positioning: "Decision-grade transit reliability read over live arrival and disruption context.",
    toolsets: ["public", "property"],
    inputSchema: TransitReliabilitySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitReliability(validateInput(TransitReliabilitySchema, input)),
  },
  {
    name: "sg_transit_transfer_risk",
    description: "Estimate missed-transfer probability and fallback options for a transfer stop and service pair.",
    surface: "canonical",
    positioning: "Decision-grade transfer-risk read for transit operations and commuter guidance.",
    toolsets: ["public", "property"],
    inputSchema: TransitTransferRiskSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitTransferRisk(validateInput(TransitTransferRiskSchema, input)),
  },
  {
    name: "sg_transit_accessible_route",
    description: "Rank route candidates by accessibility signals for wheelchair, reduced-walk, and elder-friendly modes.",
    surface: "canonical",
    positioning: "Accessibility-focused transit intelligence read for inclusive routing decisions.",
    toolsets: ["public", "property"],
    inputSchema: TransitAccessibleRouteSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitAccessibleRoute(validateInput(TransitAccessibleRouteSchema, input)),
  },
  {
    name: "sg_transit_objective_plan",
    description: "Generate tenant-aware objective transit plans with deterministic policy filtering and explainers.",
    surface: "operational",
    positioning: "Advanced transit decisioning with policy guardrails and scope memory.",
    toolsets: ["ops", "property"],
    inputSchema: TransitObjectivePlanSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitObjectivePlan(validateInput(TransitObjectivePlanSchema, input)),
  },
  {
    name: "sg_transit_counterfactual_simulate",
    description: "Run counterfactual transit-plan scenarios against a baseline to compare policy and decision deltas.",
    surface: "operational",
    positioning: "Pre-rollout safety tool for transit policy and decision changes.",
    toolsets: ["ops", "property"],
    inputSchema: TransitCounterfactualSimulateSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitCounterfactualSimulate(validateInput(TransitCounterfactualSimulateSchema, input)),
  },
  {
    name: "sg_transit_outcome_record",
    description: "Record recommendation outcomes to support transit-model quality and calibration tracking.",
    surface: "operational",
    positioning: "Closed-loop transit learning primitive for quality governance.",
    toolsets: ["ops"],
    inputSchema: TransitOutcomeRecordSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitOutcomeRecord(validateInput(TransitOutcomeRecordSchema, input)),
  },
  {
    name: "sg_transit_model_metrics",
    description: "Return transit-model quality metrics including prediction, calibration, and recommendation success rates.",
    surface: "operational",
    positioning: "Transit intelligence observability for model quality and trust.",
    toolsets: ["ops", "property"],
    inputSchema: TransitModelMetricsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitModelMetrics(validateInput(TransitModelMetricsSchema, input)),
  },
  {
    name: "sg_transit_policy_audit",
    description: "List transit policy-audit traces for governance and post-incident review.",
    surface: "operational",
    positioning: "Transit decision governance log with deterministic policy evaluations.",
    toolsets: ["ops", "property"],
    inputSchema: TransitPolicyAuditSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitPolicyAudit(validateInput(TransitPolicyAuditSchema, input)),
  },
  {
    name: "sg_transit_policy_insights",
    description: "Aggregate blocking rules and acceptance rates from transit policy-audit traces.",
    surface: "operational",
    positioning: "Transit governance insights for policy tuning and safe rollout checks.",
    toolsets: ["ops", "property"],
    inputSchema: TransitPolicyAuditSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitPolicyInsights(validateInput(TransitPolicyAuditSchema, input)),
  },
  {
    name: "sg_transit_policy_replay",
    description: "Replay a historical transit policy trace with patched constraints before production rollout.",
    surface: "operational",
    positioning: "Transit policy replay for reproducible decision-governance validation.",
    toolsets: ["ops", "property"],
    inputSchema: TransitPolicyReplaySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransitPolicyReplay(validateInput(TransitPolicyReplaySchema, input)),
  },
];
