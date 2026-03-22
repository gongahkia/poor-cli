export declare class RateLimiter {
    private tokens;
    private readonly maxTokens;
    private readonly refillPerSecond;
    private lastRefill;
    constructor(maxTokens: number, refillPerSecond: number);
    acquire(): Promise<void>;
    private refill;
}
export declare const getRateLimiter: (apiName: string) => RateLimiter;
//# sourceMappingURL=rate-limiter.d.ts.map