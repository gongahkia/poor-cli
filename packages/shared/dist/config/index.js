import { readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { TTL } from "./ttl.js";
import { RATE_LIMITS } from "./rate-limits.js";
import { TIMEOUTS } from "./timeouts.js";
const DEFAULT_CONFIG = {
    cache: { ttl: { ...TTL } },
    rateLimits: { ...RATE_LIMITS },
    timeouts: { ...TIMEOUTS },
    defaultFormat: "markdown",
    logLevel: "info",
};
const loadFileConfig = () => {
    const configPath = join(homedir(), ".sg-apis", "config.json");
    try {
        const raw = readFileSync(configPath, "utf-8");
        return JSON.parse(raw);
    }
    catch {
        return {};
    }
};
const applyEnvOverrides = (config) => {
    const logLevel = process.env["SG_APIS_LOG_LEVEL"];
    const mockUrl = process.env["MOCK_API_BASE_URL"];
    const dailyTtl = process.env["SG_APIS_CACHE_TTL_DAILY"];
    return {
        ...config,
        logLevel: logLevel !== undefined && logLevel !== ""
            ? logLevel
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
export const loadConfig = () => {
    const fileConfig = loadFileConfig();
    const merged = {
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
//# sourceMappingURL=index.js.map