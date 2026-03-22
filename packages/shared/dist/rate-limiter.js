import { RATE_LIMITS } from "./config/rate-limits.js";
export class RateLimiter {
    tokens;
    maxTokens;
    refillPerSecond;
    lastRefill;
    constructor(maxTokens, refillPerSecond) {
        this.maxTokens = maxTokens;
        this.tokens = maxTokens;
        this.refillPerSecond = refillPerSecond;
        this.lastRefill = Date.now();
    }
    async acquire() {
        this.refill();
        if (this.tokens > 0) {
            this.tokens--;
            return;
        }
        const waitMs = Math.ceil(1000 / this.refillPerSecond);
        await new Promise((resolve) => setTimeout(resolve, waitMs));
        this.refill();
        this.tokens--;
    }
    refill() {
        const now = Date.now();
        const elapsed = (now - this.lastRefill) / 1000;
        const newTokens = Math.floor(elapsed * this.refillPerSecond);
        if (newTokens > 0) {
            this.tokens = Math.min(this.maxTokens, this.tokens + newTokens);
            this.lastRefill = now;
        }
    }
}
const limiters = new Map();
export const getRateLimiter = (apiName) => {
    const existing = limiters.get(apiName);
    if (existing !== undefined) {
        return existing;
    }
    const config = RATE_LIMITS[apiName] ?? { maxTokens: 10, refillPerSecond: 2 };
    const limiter = new RateLimiter(config.maxTokens, config.refillPerSecond);
    limiters.set(apiName, limiter);
    return limiter;
};
//# sourceMappingURL=rate-limiter.js.map