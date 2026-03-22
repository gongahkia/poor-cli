import type { OutputFormat } from "../types/index.js";
import type { RateLimitConfig } from "./rate-limits.js";
export type Config = {
    readonly cache: {
        readonly ttl: Readonly<Record<string, number>>;
    };
    readonly rateLimits: Readonly<Record<string, RateLimitConfig>>;
    readonly timeouts: Readonly<Record<string, number>>;
    readonly defaultFormat: OutputFormat;
    readonly logLevel: "debug" | "info" | "warn" | "error";
    readonly mockApiBaseUrl?: string;
};
export declare const loadConfig: () => Config;
//# sourceMappingURL=index.d.ts.map