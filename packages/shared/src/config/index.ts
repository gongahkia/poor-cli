import { readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import type { OutputFormat } from "../types/index.js";
import { TTL } from "./ttl.js";
import { RATE_LIMITS } from "./rate-limits.js";
import type { RateLimitConfig } from "./rate-limits.js";
import { TIMEOUTS } from "./timeouts.js";

export type Config = {
  readonly cache: { readonly ttl: Readonly<Record<string, number>> };
  readonly rateLimits: Readonly<Record<string, RateLimitConfig>>;
  readonly timeouts: Readonly<Record<string, number>>;
  readonly defaultFormat: OutputFormat;
  readonly logLevel: "debug" | "info" | "warn" | "error";
  readonly mockApiBaseUrl?: string;
};

const DEFAULT_CONFIG: Config = {
  cache: { ttl: { ...TTL } },
  rateLimits: { ...RATE_LIMITS },
  timeouts: { ...TIMEOUTS },
  defaultFormat: "markdown",
  logLevel: "info",
};

const loadFileConfig = (): Partial<Config> => {
  const configPath = join(homedir(), ".sg-apis", "config.json");
  try {
    const raw = readFileSync(configPath, "utf-8");
    return JSON.parse(raw) as Partial<Config>;
  } catch {
    return {};
  }
};

const applyEnvOverrides = (config: Config): Config => {
  const logLevel = process.env["SG_APIS_LOG_LEVEL"];
  const mockUrl = process.env["MOCK_API_BASE_URL"];
  const dailyTtl = process.env["SG_APIS_CACHE_TTL_DAILY"];

  return {
    ...config,
    logLevel:
      logLevel !== undefined && logLevel !== ""
        ? (logLevel as Config["logLevel"])
        : config.logLevel,
    ...(mockUrl !== undefined && mockUrl !== ""
      ? { mockApiBaseUrl: mockUrl }
      : config.mockApiBaseUrl !== undefined
        ? { mockApiBaseUrl: config.mockApiBaseUrl }
        : {}),
    cache: {
      ...config.cache,
      ttl: {
        ...config.cache.ttl,
        ...(dailyTtl !== undefined && dailyTtl !== ""
          ? { DAILY: parseInt(dailyTtl, 10) }
          : {}),
      },
    },
  };
};

export const loadConfig = (): Config => {
  const fileConfig = loadFileConfig();
  const merged: Config = {
    ...DEFAULT_CONFIG,
    ...fileConfig,
    cache: {
      ttl: { ...DEFAULT_CONFIG.cache.ttl, ...fileConfig.cache?.ttl },
    },
    rateLimits: { ...DEFAULT_CONFIG.rateLimits, ...fileConfig.rateLimits },
    timeouts: { ...DEFAULT_CONFIG.timeouts, ...fileConfig.timeouts },
  };
  return applyEnvOverrides(merged);
};
