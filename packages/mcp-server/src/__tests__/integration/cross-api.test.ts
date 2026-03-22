import { describe, it, expect } from "vitest";
import { buildCacheKey } from "../../middleware/cache-middleware.js";

describe("Cross-API Integration", () => {
  it("generates unique cache keys per API", () => {
    const singstatKey = buildCacheKey("singstat", "search", { keyword: "GDP" });
    const masKey = buildCacheKey("mas", "search", { keyword: "GDP" });
    expect(singstatKey).not.toBe(masKey);
  });

  it("cache key is deterministic regardless of param order", () => {
    const key1 = buildCacheKey("api", "op", { a: 1, b: 2 });
    const key2 = buildCacheKey("api", "op", { b: 2, a: 1 });
    expect(key1).toBe(key2);
  });

  it("different params produce different cache keys", () => {
    const key1 = buildCacheKey("mas", "rates", { currency: "USD" });
    const key2 = buildCacheKey("mas", "rates", { currency: "EUR" });
    expect(key1).not.toBe(key2);
  });
});
