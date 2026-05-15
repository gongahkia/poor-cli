import { ApiError } from "@sg-apis/shared";
import { probeAcraLookupReadiness } from "../apis/acra/client.js";
import { probeTinyFishSearchReadiness } from "../apis/tinyfish/client.js";
import { probeDatagovDatastoreHealth } from "../tools/health-check.js";

export type GatewayReadinessLevel = "ready" | "degraded" | "failing";
export type GatewayServiceStatus = "ready" | "unconfigured" | "failing";

export type GatewayServiceReadiness = {
  readonly status: GatewayServiceStatus;
  readonly message: string;
  readonly observedAt: string;
  readonly latencyMs?: number;
  readonly configured?: boolean;
  readonly errorCode?: string;
  readonly retryable?: boolean;
  readonly details?: Readonly<Record<string, string | number | boolean>>;
};

export type GatewayHealthPayload = {
  readonly status: "ok" | "degraded";
  readonly readiness: GatewayReadinessLevel;
  readonly tools: number;
  readonly runtime: {
    readonly startedAt: string;
    readonly uptimeSeconds: number;
    readonly observedAt: string;
  };
  readonly services: {
    readonly gateway: GatewayServiceReadiness;
    readonly datagovDatastore: GatewayServiceReadiness;
    readonly acraLookup: GatewayServiceReadiness;
    readonly tinyfish: GatewayServiceReadiness & {
      readonly configured: boolean;
      readonly mode: "web-discovery-only";
    };
  };
};

const READINESS_CACHE_TTL_MS = 60_000;

let cachedServiceReadiness:
  | {
      readonly expiresAt: number;
      readonly services: Omit<GatewayHealthPayload["services"], "gateway">;
    }
  | null = null;
let inFlightServiceReadiness: Promise<Omit<GatewayHealthPayload["services"], "gateway">> | null = null;

const toObservedAt = (): string => new Date().toISOString();

const sanitizeReadinessError = (
  error: unknown,
): Pick<GatewayServiceReadiness, "message" | "errorCode" | "retryable"> => {
  if (error instanceof ApiError) {
    const statusMessage =
      error.statusCode === 401 || error.statusCode === 403
        ? "Upstream rejected the readiness probe."
        : error.statusCode === 408
          ? "Upstream readiness probe timed out."
          : error.statusCode === 429
            ? "Upstream rate limit reached during readiness probe."
            : error.statusCode >= 500
              ? "Upstream service failed the readiness probe."
              : "Upstream readiness probe failed.";

    return {
      message: statusMessage,
      errorCode: error.code,
      retryable: error.retryable,
    };
  }

  return {
    message: "Readiness probe failed.",
    errorCode: error instanceof Error ? error.name : "READINESS_PROBE_FAILED",
    retryable: true,
  };
};

const runReadinessProbe = async <TDetails extends Readonly<Record<string, string | number | boolean>>>(
  probe: () => Promise<TDetails>,
  readyMessage: (details: TDetails) => string,
): Promise<GatewayServiceReadiness> => {
  const startedAt = Date.now();
  try {
    const details = await probe();
    return {
      status: "ready",
      message: readyMessage(details),
      observedAt: toObservedAt(),
      latencyMs: Date.now() - startedAt,
      details,
    };
  } catch (error) {
    return {
      status: "failing",
      observedAt: toObservedAt(),
      latencyMs: Date.now() - startedAt,
      ...sanitizeReadinessError(error),
    };
  }
};

const checkDatagovDatastoreReadiness = async (): Promise<GatewayServiceReadiness> =>
  runReadinessProbe(
    async () => {
      await probeDatagovDatastoreHealth();
      return {
        source: "data.gov.sg datastore",
        representativeTool: "sg_hdb_resale_prices",
      };
    },
    () => "data.gov.sg datastore returned rows through the runtime client.",
  );

const checkAcraLookupReadiness = async (): Promise<GatewayServiceReadiness> =>
  runReadinessProbe(
    async () => {
      const result = await probeAcraLookupReadiness();
      return {
        source: "ACRA entity shards on data.gov.sg",
        representativeTool: "sg_acra_entities",
        resourceId: result.resourceId,
        recordCount: result.recordCount,
        fieldCount: result.fieldCount,
      };
    },
    (details) =>
      `ACRA lookup path returned ${details.recordCount} row through data.gov.sg.`,
  );

const checkTinyFishReadiness = async (): Promise<GatewayHealthPayload["services"]["tinyfish"]> => {
  const startedAt = Date.now();
  try {
    const result = await probeTinyFishSearchReadiness();
    if (!result.configured) {
      return {
        status: "unconfigured",
        configured: false,
        mode: "web-discovery-only",
        message: "TinyFish web discovery is not configured.",
        observedAt: toObservedAt(),
        latencyMs: Date.now() - startedAt,
      };
    }

    return {
      status: "ready",
      configured: true,
      mode: "web-discovery-only",
      message: "TinyFish search accepted the readiness query.",
      observedAt: toObservedAt(),
      latencyMs: Date.now() - startedAt,
      details: {
        source: "TinyFish Search",
        resultCount: result.resultCount ?? 0,
      },
    };
  } catch (error) {
    return {
      status: "failing",
      configured: true,
      mode: "web-discovery-only",
      observedAt: toObservedAt(),
      latencyMs: Date.now() - startedAt,
      ...sanitizeReadinessError(error),
    };
  }
};

const resolveServiceReadiness = async (): Promise<Omit<GatewayHealthPayload["services"], "gateway">> => {
  const now = Date.now();
  if (cachedServiceReadiness !== null && cachedServiceReadiness.expiresAt > now) {
    return cachedServiceReadiness.services;
  }
  if (inFlightServiceReadiness !== null) {
    return inFlightServiceReadiness;
  }

  inFlightServiceReadiness = Promise.all([
    checkDatagovDatastoreReadiness(),
    checkAcraLookupReadiness(),
    checkTinyFishReadiness(),
  ])
    .then(([datagovDatastore, acraLookup, tinyfish]) => {
      const services = {
        datagovDatastore,
        acraLookup,
        tinyfish,
      };
      cachedServiceReadiness = {
        expiresAt: Date.now() + READINESS_CACHE_TTL_MS,
        services,
      };
      return services;
    })
    .finally(() => {
      inFlightServiceReadiness = null;
    });

  return inFlightServiceReadiness;
};

export const getGatewayHealthPayload = async (params: {
  readonly toolCount: number;
  readonly startedAt: Date;
}): Promise<GatewayHealthPayload> => {
  const observedAt = toObservedAt();
  const services = await resolveServiceReadiness();
  const requiredReady =
    services.datagovDatastore.status === "ready" && services.acraLookup.status === "ready";
  const optionalReady = services.tinyfish.status === "ready";
  const readiness: GatewayReadinessLevel = requiredReady
    ? optionalReady
      ? "ready"
      : "degraded"
    : "failing";

  return {
    status: requiredReady ? "ok" : "degraded",
    readiness,
    tools: params.toolCount,
    runtime: {
      startedAt: params.startedAt.toISOString(),
      uptimeSeconds: Math.floor(process.uptime()),
      observedAt,
    },
    services: {
      gateway: {
        status: "ready",
        message: "HTTP gateway is reachable.",
        observedAt,
        details: {
          toolCount: params.toolCount,
        },
      },
      ...services,
    },
  };
};
