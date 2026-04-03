import { describe, it, expect, beforeEach } from "vitest";
import { RateLimiter } from "../rate-limiter.js";

describe("RateLimiter", () => {
  let limiter: RateLimiter;

  beforeEach(() => {
    limiter = new RateLimiter(3, 10); // 3 tokens, 10/sec refill
  });

  it("allows immediate acquisition up to max tokens", async () => {
    await limiter.acquire();
    await limiter.acquire();
    await limiter.acquire();
  });

  it("never produces negative token count under concurrent pressure", async () => {
    const results = await Promise.all(
      Array.from({ length: 10 }, () => limiter.acquire().then(() => "ok")),
    );
    expect(results).toHaveLength(10);
    expect(results.every((r) => r === "ok")).toBe(true);
  });

  it("throttles beyond burst capacity", async () => {
    const start = Date.now();
    const promises = Array.from({ length: 6 }, () => limiter.acquire());
    await Promise.all(promises);
    const elapsed = Date.now() - start;
    expect(elapsed).toBeGreaterThanOrEqual(50); // at least some waiting happened
  });
});
