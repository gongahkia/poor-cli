import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { buildCacheKey, closeCache, getCache, withCache } from "../cache-middleware.js";

beforeEach(() => {
  getCache().clear();
});

afterEach(() => {
  closeCache();
});

describe("cache-middleware", () => {
  it("produces same cache key regardless of param order", () => {
    const key1 = buildCacheKey("api", "op", { a: 1, b: 2 });
    const key2 = buildCacheKey("api", "op", { b: 2, a: 1 });
    expect(key1).toBe(key2);
  });

  it("produces same cache key regardless of nested param order", () => {
    const key1 = buildCacheKey("datagov", "datastore", {
      filters: { entity_name: "DBS PTE. LTD.", uen: "197700546G" },
      limit: 1,
      resourceId: "d_acbc938ec77af18f94cecc4a7c9ec720",
    });
    const key2 = buildCacheKey("datagov", "datastore", {
      resourceId: "d_acbc938ec77af18f94cecc4a7c9ec720",
      limit: 1,
      filters: { uen: "197700546G", entity_name: "DBS PTE. LTD." },
    });
    expect(key1).toBe(key2);
  });

  it("distinguishes nested filter values", () => {
    const key1 = buildCacheKey("datagov", "datastore", {
      filters: { uen: "197700546G" },
      limit: 1,
      resourceId: "d_acbc938ec77af18f94cecc4a7c9ec720",
    });
    const key2 = buildCacheKey("datagov", "datastore", {
      filters: { uen: "198100341G" },
      limit: 1,
      resourceId: "d_acbc938ec77af18f94cecc4a7c9ec720",
    });
    expect(key1).not.toBe(key2);
  });

  it("produces different keys for different APIs", () => {
    const key1 = buildCacheKey("singstat", "search", { keyword: "GDP" });
    const key2 = buildCacheKey("mas", "search", { keyword: "GDP" });
    expect(key1).not.toBe(key2);
  });

  it("produces different keys for different operations", () => {
    const key1 = buildCacheKey("singstat", "search", { keyword: "GDP" });
    const key2 = buildCacheKey("singstat", "table", { keyword: "GDP" });
    expect(key1).not.toBe(key2);
  });

  it("includes api name and operation in key", () => {
    const key = buildCacheKey("singstat", "search", { keyword: "GDP" });
    expect(key).toContain("singstat");
    expect(key).toContain("search");
  });

  it("serves stale cache data when an upstream refresh fails", async () => {
    getCache().set("datagov:datastore:test", JSON.stringify({ records: [{ uen: "197700546G" }] }), 0);

    const result = await withCache(
      "datagov:datastore:test",
      "DAILY",
      async () => {
        throw new Error("data.gov.sg unavailable");
      },
    );

    expect(result).toEqual({
      cached: true,
      stale: true,
      data: { records: [{ uen: "197700546G" }] },
    });
  });

  it("deduplicates concurrent refreshes for the same cache key", async () => {
    const fetcher = vi.fn(async () => ({ records: [{ uen: "03591300B" }] }));

    const [first, second] = await Promise.all([
      withCache("datagov:datastore:dedupe", "DAILY", fetcher),
      withCache("datagov:datastore:dedupe", "DAILY", fetcher),
    ]);

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(first.data).toEqual(second.data);
  });
});
