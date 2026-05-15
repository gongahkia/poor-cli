export type GatewayRouteMetric = {
  readonly method: string;
  readonly route: string;
  readonly count: number;
  readonly errorCount: number;
  readonly totalDurationMs: number;
  readonly lastStatus: number;
  readonly lastDurationMs: number;
  readonly lastObservedAt: string;
};

export type GatewayUpstreamFailureMetric = {
  readonly tool: string;
  readonly code: string;
  readonly count: number;
  readonly lastObservedAt: string;
};

const routeMetrics = new Map<string, GatewayRouteMetric>();
const upstreamFailureMetrics = new Map<string, GatewayUpstreamFailureMetric>();

const metricKey = (...parts: readonly string[]): string => parts.join("\u0000");
const observedNow = (): string => new Date().toISOString();

export const recordGatewayRequest = (params: {
  readonly method: string;
  readonly route: string;
  readonly status: number;
  readonly durationMs: number;
}): void => {
  const key = metricKey(params.method, params.route);
  const existing = routeMetrics.get(key);
  routeMetrics.set(key, {
    method: params.method,
    route: params.route,
    count: (existing?.count ?? 0) + 1,
    errorCount: (existing?.errorCount ?? 0) + (params.status >= 400 ? 1 : 0),
    totalDurationMs: (existing?.totalDurationMs ?? 0) + params.durationMs,
    lastStatus: params.status,
    lastDurationMs: params.durationMs,
    lastObservedAt: observedNow(),
  });
};

export const recordUpstreamFailures = (
  tool: string,
  codes: readonly string[],
): void => {
  for (const code of codes) {
    const normalizedCode = code.trim();
    if (normalizedCode === "") {
      continue;
    }

    const key = metricKey(tool, normalizedCode);
    const existing = upstreamFailureMetrics.get(key);
    upstreamFailureMetrics.set(key, {
      tool,
      code: normalizedCode,
      count: (existing?.count ?? 0) + 1,
      lastObservedAt: observedNow(),
    });
  }
};

export const getGatewayMetricsSnapshot = (params: {
  readonly startedAt: Date;
}): {
  readonly observedAt: string;
  readonly runtime: {
    readonly startedAt: string;
    readonly uptimeSeconds: number;
  };
  readonly requests: {
    readonly total: number;
    readonly routes: readonly (GatewayRouteMetric & { readonly averageDurationMs: number })[];
  };
  readonly upstreamFailures: {
    readonly total: number;
    readonly codes: readonly GatewayUpstreamFailureMetric[];
  };
} => {
  const routes = Array.from(routeMetrics.values())
    .map((metric) => ({
      ...metric,
      averageDurationMs: Math.round(metric.totalDurationMs / metric.count),
    }))
    .sort((a, b) => b.count - a.count || a.route.localeCompare(b.route));
  const upstreamFailures = Array.from(upstreamFailureMetrics.values())
    .sort((a, b) => b.count - a.count || a.code.localeCompare(b.code));

  return {
    observedAt: observedNow(),
    runtime: {
      startedAt: params.startedAt.toISOString(),
      uptimeSeconds: Math.floor(process.uptime()),
    },
    requests: {
      total: routes.reduce((sum, metric) => sum + metric.count, 0),
      routes,
    },
    upstreamFailures: {
      total: upstreamFailures.reduce((sum, metric) => sum + metric.count, 0),
      codes: upstreamFailures,
    },
  };
};
