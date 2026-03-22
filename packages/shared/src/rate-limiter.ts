import { getRateLimit } from "./config/index.js";

export class RateLimiter {
  private tokens: number;
  private readonly maxTokens: number;
  private readonly refillPerSecond: number;
  private lastRefill: number;

  constructor(maxTokens: number, refillPerSecond: number) {
    this.maxTokens = maxTokens;
    this.tokens = maxTokens;
    this.refillPerSecond = refillPerSecond;
    this.lastRefill = Date.now();
  }

  async acquire(): Promise<void> {
    this.refill();
    if (this.tokens > 0) {
      this.tokens--;
      return;
    }
    const waitMs = Math.ceil(1000 / this.refillPerSecond);
    await new Promise<void>((resolve) => setTimeout(resolve, waitMs));
    this.refill();
    this.tokens--;
  }

  private refill(): void {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    const newTokens = Math.floor(elapsed * this.refillPerSecond);
    if (newTokens > 0) {
      this.tokens = Math.min(this.maxTokens, this.tokens + newTokens);
      this.lastRefill = now;
    }
  }
}

const limiters = new Map<string, RateLimiter>();

export const resetRateLimiters = (): void => {
  limiters.clear();
};

export const getRateLimiter = (apiName: string): RateLimiter => {
  const existing = limiters.get(apiName);
  if (existing !== undefined) {
    return existing;
  }
  const config = getRateLimit(apiName);
  const limiter = new RateLimiter(config.maxTokens, config.refillPerSecond);
  limiters.set(apiName, limiter);
  return limiter;
};
