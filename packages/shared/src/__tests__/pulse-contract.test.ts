import { describe, expect, it } from "vitest";
import {
  evaluatePulseFreshness,
  isPulseSeverityAtLeast,
  PULSE_SIGNAL_CATEGORIES,
  PULSE_SIGNAL_SEVERITIES,
  resolvePulseSourceHealthStatus,
  type PulseSignal,
  type PulseSourceHealth,
} from "../index.js";

describe("Swee Pulse contract", () => {
  it("exports normalized categories and ordered severities", () => {
    expect(PULSE_SIGNAL_CATEGORIES).toEqual(["mobility", "weather", "source_health"]);
    expect(PULSE_SIGNAL_SEVERITIES).toEqual(["info", "watch", "disrupted", "critical"]);
    expect(isPulseSeverityAtLeast("disrupted", "watch")).toBe(true);
    expect(isPulseSeverityAtLeast("info", "critical")).toBe(false);
  });

  it("evaluates source freshness against an explicit max age", () => {
    const freshness = evaluatePulseFreshness({
      observedAt: "2026-05-22T07:00:00.000Z",
      upstreamTimestamp: "2026-05-22T06:55:00.000Z",
      maxAgeSeconds: 600,
      now: new Date("2026-05-22T07:00:00.000Z"),
    });

    expect(freshness).toEqual({
      observedAt: "2026-05-22T07:00:00.000Z",
      upstreamTimestamp: "2026-05-22T06:55:00.000Z",
      maxAgeSeconds: 600,
      status: "fresh",
      ageSeconds: 300,
    });

    expect(evaluatePulseFreshness({
      observedAt: "2026-05-22T07:00:00.000Z",
      upstreamTimestamp: "2026-05-22T06:00:00.000Z",
      maxAgeSeconds: 600,
      now: new Date("2026-05-22T07:00:00.000Z"),
    }).status).toBe("stale");

    expect(evaluatePulseFreshness({
      observedAt: "2026-05-22T07:00:00.000Z",
      upstreamTimestamp: null,
      maxAgeSeconds: 600,
      now: new Date("2026-05-22T07:00:00.000Z"),
    }).status).toBe("unknown");
  });

  it("models provenance and evidence gaps on signals and source health", () => {
    const freshness = evaluatePulseFreshness({
      observedAt: "2026-05-22T07:00:00.000Z",
      upstreamTimestamp: "2026-05-22T06:58:00.000Z",
      maxAgeSeconds: 900,
      now: new Date("2026-05-22T07:00:00.000Z"),
    });
    const signal = {
      id: "mobility:lta:incident:1",
      category: "mobility",
      severity: "watch",
      title: "Traffic incident on PIE",
      description: "LTA reported a traffic incident affecting a major route.",
      source: "LTA",
      sourceTool: "sg_lta_traffic_incidents",
      observedAt: "2026-05-22T07:00:00.000Z",
      upstreamTimestamp: "2026-05-22T06:58:00.000Z",
      location: { lat: 1.3521, lng: 103.8198 },
      provenance: [{
        source: "LTA",
        sourceTool: "sg_lta_traffic_incidents",
        observedAt: "2026-05-22T07:00:00.000Z",
        upstreamTimestamp: "2026-05-22T06:58:00.000Z",
        recordCount: 1,
        sourceUrl: "https://datamall.lta.gov.sg/",
      }],
      freshness,
      gaps: [],
      recommendedAction: "Monitor the incident before routing drivers through the corridor.",
      raw: { incidentId: "1" },
    } satisfies PulseSignal;

    const sourceHealth = {
      source: "LTA",
      sourceTool: "sg_lta_traffic_incidents",
      status: "ready",
      observedAt: "2026-05-22T07:00:00.000Z",
      recordCount: 1,
      freshness,
      gaps: [],
      provenance: signal.provenance,
    } satisfies PulseSourceHealth;

    expect(signal.provenance[0]?.sourceTool).toBe("sg_lta_traffic_incidents");
    expect(signal.gaps).toHaveLength(0);
    expect(resolvePulseSourceHealthStatus(sourceHealth)).toBe("ready");
    expect(resolvePulseSourceHealthStatus({ ...sourceHealth, gaps: [{ code: "SOURCE_EMPTY", message: "No rows returned." }] })).toBe("gap");
  });
});
