import { readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import type { OutputFormat } from "../types/index.js";
import { TTL } from "./ttl.js";
import type { TTLKey } from "./ttl.js";
import { RATE_LIMITS } from "./rate-limits.js";
import type { RateLimitConfig } from "./rate-limits.js";
import { TIMEOUTS } from "./timeouts.js";

export type Config = {
  readonly cache: { readonly ttl: Readonly<Record<string, number>> };
  readonly rateLimits: Readonly<Record<string, RateLimitConfig>>;
  readonly timeouts: Readonly<Record<string, number>>;
  readonly defaultFormat: OutputFormat;
  readonly logLevel: "debug" | "info" | "warn" | "error";
};

const OUTPUT_FORMATS = new Set<OutputFormat>(["json", "markdown", "csv", "geojson"]);
const LOG_LEVELS = new Set<Config["logLevel"]>(["debug", "info", "warn", "error"]);
const DEFAULT_RATE_LIMIT: RateLimitConfig = { maxTokens: 10, refillPerSecond: 2 };
const TTL_KEYS = Object.keys(TTL) as TTLKey[];
const RATE_LIMIT_APIS = Object.keys(RATE_LIMITS);
const TIMEOUT_APIS = Object.keys(TIMEOUTS);

const DEFAULT_CONFIG: Config = {
  cache: { ttl: { ...TTL } },
  rateLimits: { ...RATE_LIMITS },
  timeouts: { ...TIMEOUTS },
  defaultFormat: "markdown",
  logLevel: "info",
};

let cachedConfig: Config | null = null;

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
  const dailyTtl = process.env["SG_APIS_CACHE_TTL_DAILY"];
  const parsedDailyTtl = dailyTtl !== undefined && dailyTtl !== "" ? Number(dailyTtl) : undefined;

  return {
    ...config,
    logLevel:
      logLevel !== undefined && logLevel !== "" && LOG_LEVELS.has(logLevel as Config["logLevel"])
        ? (logLevel as Config["logLevel"])
        : config.logLevel,
    cache: {
      ...config.cache,
      ttl: {
        ...config.cache.ttl,
        ...(parsedDailyTtl !== undefined && Number.isFinite(parsedDailyTtl) && parsedDailyTtl > 0
          ? { DAILY: parsedDailyTtl }
          : {}),
      },
    },
  };
};

const readConfig = (): Config => {
  const fileConfig = loadFileConfig();
  const merged: Config = {
    ...DEFAULT_CONFIG,
    ...fileConfig,
    cache: {
      ttl: { ...DEFAULT_CONFIG.cache.ttl, ...fileConfig.cache?.ttl },
    },
    rateLimits: { ...DEFAULT_CONFIG.rateLimits, ...fileConfig.rateLimits },
    timeouts: { ...DEFAULT_CONFIG.timeouts, ...fileConfig.timeouts },
    defaultFormat: OUTPUT_FORMATS.has(fileConfig.defaultFormat as OutputFormat)
      ? (fileConfig.defaultFormat as OutputFormat)
      : DEFAULT_CONFIG.defaultFormat,
    logLevel: LOG_LEVELS.has(fileConfig.logLevel as Config["logLevel"])
      ? (fileConfig.logLevel as Config["logLevel"])
      : DEFAULT_CONFIG.logLevel,
  };
  return applyEnvOverrides(merged);
};

export const loadConfig = (): Config => {
  if (cachedConfig === null) {
    cachedConfig = readConfig();
  }
  return cachedConfig;
};

export const resetConfigCache = (): void => {
  cachedConfig = null;
};

export const getCacheTtl = (ttlKey: TTLKey): number => {
  return loadConfig().cache.ttl[ttlKey] ?? TTL[ttlKey];
};

export const getRateLimit = (apiName: string): RateLimitConfig => {
  return loadConfig().rateLimits[apiName] ?? RATE_LIMITS[apiName] ?? DEFAULT_RATE_LIMIT;
};

export const getTimeout = (apiName: string): number => {
  return loadConfig().timeouts[apiName] ?? TIMEOUTS[apiName] ?? 10000;
};

export const resolveOutputFormat = (format?: OutputFormat): OutputFormat => {
  return format ?? loadConfig().defaultFormat;
};

const parsePositiveInteger = (key: string, value: string): number => {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`Invalid value for ${key}: expected a positive integer`);
  }
  return parsed;
};

const parsePositiveNumber = (key: string, value: string): number => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`Invalid value for ${key}: expected a positive number`);
  }
  return parsed;
};

export const getSupportedConfigKeys = (): string[] => {
  return [
    "defaultFormat",
    "logLevel",
    ...TTL_KEYS.map((ttlKey) => `cache.ttl.${ttlKey}`),
    ...RATE_LIMIT_APIS.flatMap((apiName) => [
      `rateLimits.${apiName}.maxTokens`,
      `rateLimits.${apiName}.refillPerSecond`,
    ]),
    ...TIMEOUT_APIS.map((apiName) => `timeouts.${apiName}`),
  ];
};

export const parseMutableConfigValue = (key: string, value: string): string | number => {
  if (key === "defaultFormat") {
    if (!OUTPUT_FORMATS.has(value as OutputFormat)) {
      throw new Error(`Invalid value for ${key}: expected one of ${Array.from(OUTPUT_FORMATS).join(", ")}`);
    }
    return value;
  }

  if (key === "logLevel") {
    if (!LOG_LEVELS.has(value as Config["logLevel"])) {
      throw new Error(`Invalid value for ${key}: expected one of ${Array.from(LOG_LEVELS).join(", ")}`);
    }
    return value;
  }

  if (TTL_KEYS.some((ttlKey) => key === `cache.ttl.${ttlKey}`)) {
    return parsePositiveInteger(key, value);
  }

  if (TIMEOUT_APIS.some((apiName) => key === `timeouts.${apiName}`)) {
    return parsePositiveInteger(key, value);
  }

  for (const apiName of RATE_LIMIT_APIS) {
    if (key === `rateLimits.${apiName}.maxTokens`) {
      return parsePositiveInteger(key, value);
    }
    if (key === `rateLimits.${apiName}.refillPerSecond`) {
      return parsePositiveNumber(key, value);
    }
  }

  throw new Error(`Unsupported config key: ${key}`);
};
