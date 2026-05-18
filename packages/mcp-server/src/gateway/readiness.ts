import { ApiError } from "@dude/shared";
import {
  generateText,
  ProviderRequestError,
  resolveAiProviderConfig,
  type AiProvider,
} from "../ai/providers.js";
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
    readonly analystMemo: GatewayServiceReadiness & {
      readonly configured: boolean;
      readonly provider: AiProvider;
      readonly model: string;
    };
  };
};

const READINESS_CACHE_TTL_MS = 60_000;

const PROVIDER_KEY_ENV: Record<AiProvider, string> = {
  anthropic: "ANTHROPIC_API_KEY",
  google: "GOOGLE_API_KEY",
  openai: "OPENAI_API_KEY",
};

let cachedServiceReadiness: {
  readonly expiresAt: number;
  readonly services: Omit<GatewayHealthPayload["services"], "gateway">;
} | null = null;
let inFlightServiceReadiness: Promise<Omit<GatewayHealthPayload["services"], "gateway">> | null =
  null;

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

const sanitizeProviderReadinessError = (
  error: unknown,
  provider: AiProvider,
): Pick<GatewayServiceReadiness, "message" | "errorCode" | "retryable"> => {
  if (error instanceof ProviderRequestError) {
    if (error.status === 401 || error.status === 403) {
      return {
        message: `${provider} credentials were rejected by the provider. Check ${PROVIDER_KEY_ENV[provider]} on the REST gateway process.`,
        errorCode: "AI_PROVIDER_AUTH_FAILED",
        retryable: false,
      };
    }

    if (error.status === 429) {
      return {
        message: `${provider} rate limit reached during the analyst memo readiness probe.`,
        errorCode: "AI_PROVIDER_RATE_LIMITED",
        retryable: true,
      };
    }

    return {
      message: `${provider} provider rejected the analyst memo readiness probe with HTTP ${error.status}.`,
      errorCode: error.status >= 500 ? "AI_PROVIDER_UPSTREAM_FAILED" : "AI_PROVIDER_REQUEST_FAILED",
      retryable: error.status >= 500,
    };
  }

  return {
    message: error instanceof Error ? error.message : "Analyst memo readiness probe failed.",
    errorCode: error instanceof Error ? error.name : "AI_PROVIDER_READINESS_FAILED",
    retryable: true,
  };
};

const runReadinessProbe = async <
  TDetails extends Readonly<Record<string, string | number | boolean>>,
>(
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
    (details) => `ACRA lookup path returned ${details.recordCount} row through data.gov.sg.`,
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

const checkAnalystMemoReadiness = async (): Promise<
  GatewayHealthPayload["services"]["analystMemo"]
> => {
  const startedAt = Date.now();
  const config = resolveAiProviderConfig();

  if (!config.configured) {
    return {
      status: "unconfigured",
      configured: false,
      provider: config.provider,
      model: config.model,
      message: config.reason.message,
      errorCode: config.reason.code,
      observedAt: toObservedAt(),
      latencyMs: Date.now() - startedAt,
      details: {
        credentialLocation: "REST gateway process environment",
        provider: config.provider,
        requiredEnvVar: PROVIDER_KEY_ENV[config.provider],
        model: config.model,
      },
    };
  }

  try {
    await generateText(
      {
        maxTokens: 8,
        prompt: "Return the single word ok.",
        system: "You are a readiness probe. Return only the requested token.",
        temperature: 0,
      },
      config,
    );

    return {
      status: "ready",
      configured: true,
      provider: config.provider,
      model: config.model,
      message: "Analyst memo provider accepted the readiness probe.",
      observedAt: toObservedAt(),
      latencyMs: Date.now() - startedAt,
      details: {
        credentialLocation: "REST gateway process environment",
        provider: config.provider,
        requiredEnvVar: PROVIDER_KEY_ENV[config.provider],
        model: config.model,
      },
    };
  } catch (error) {
    return {
      status: "failing",
      configured: true,
      provider: config.provider,
      model: config.model,
      observedAt: toObservedAt(),
      latencyMs: Date.now() - startedAt,
      details: {
        credentialLocation: "REST gateway process environment",
        provider: config.provider,
        requiredEnvVar: PROVIDER_KEY_ENV[config.provider],
        model: config.model,
      },
      ...sanitizeProviderReadinessError(error, config.provider),
    };
  }
};

const resolveServiceReadiness = async (): Promise<
  Omit<GatewayHealthPayload["services"], "gateway">
> => {
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
    checkAnalystMemoReadiness(),
  ])
    .then(([datagovDatastore, acraLookup, tinyfish, analystMemo]) => {
      const services = {
        datagovDatastore,
        acraLookup,
        tinyfish,
        analystMemo,
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
  readonly gateway?: GatewayServiceReadiness;
  readonly toolCount: number;
  readonly startedAt: Date;
}): Promise<GatewayHealthPayload> => {
  const observedAt = toObservedAt();
  const services = await resolveServiceReadiness();
  const gateway = params.gateway ?? {
    status: "ready" as const,
    message: "HTTP gateway is reachable.",
    observedAt,
    details: {
      toolCount: params.toolCount,
    },
  };
  const requiredReady =
    gateway.status === "ready"
    && services.datagovDatastore.status === "ready"
    && services.acraLookup.status === "ready";
  const optionalReady =
    services.tinyfish.status === "ready" && services.analystMemo.status === "ready";
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
      gateway,
      ...services,
    },
  };
};
