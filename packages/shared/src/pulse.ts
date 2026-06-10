import type {
  PulseFreshness,
  PulseFreshnessStatus,
  PulseSignalCategory,
  PulseSignalSeverity,
  PulseSourceHealth,
} from "./types/index.js";

export const PULSE_SIGNAL_CATEGORIES = [
  "mobility",
  "weather",
  "source_health",
] as const satisfies readonly PulseSignalCategory[];

export const PULSE_SIGNAL_SEVERITIES = [
  "info",
  "watch",
  "disrupted",
  "critical",
] as const satisfies readonly PulseSignalSeverity[];

const SEVERITY_RANK: Readonly<Record<PulseSignalSeverity, number>> = {
  info: 0,
  watch: 1,
  disrupted: 2,
  critical: 3,
};

export const isPulseSeverityAtLeast = (
  severity: PulseSignalSeverity,
  threshold: PulseSignalSeverity,
): boolean => SEVERITY_RANK[severity] >= SEVERITY_RANK[threshold];

export const evaluatePulseFreshness = (params: {
  readonly observedAt: string;
  readonly upstreamTimestamp: string | null;
  readonly maxAgeSeconds: number;
  readonly now?: Date;
}): PulseFreshness => {
  const nowMs = params.now?.getTime() ?? Date.now();
  const upstreamMs = params.upstreamTimestamp === null
    ? NaN
    : Date.parse(params.upstreamTimestamp);
  const ageSeconds = Number.isFinite(upstreamMs)
    ? Math.max(0, Math.floor((nowMs - upstreamMs) / 1000))
    : null;
  const status: PulseFreshnessStatus = ageSeconds === null
    ? "unknown"
    : ageSeconds <= params.maxAgeSeconds
      ? "fresh"
      : "stale";

  return {
    observedAt: params.observedAt,
    upstreamTimestamp: params.upstreamTimestamp,
    maxAgeSeconds: params.maxAgeSeconds,
    status,
    ageSeconds,
  };
};

export const resolvePulseSourceHealthStatus = (
  source: Pick<PulseSourceHealth, "freshness" | "gaps" | "recordCount">,
): PulseSourceHealth["status"] => {
  if (source.gaps.length > 0 || source.recordCount === 0 || source.freshness.status === "unknown") {
    return "gap";
  }
  return source.freshness.status === "stale" ? "stale" : "ready";
};
