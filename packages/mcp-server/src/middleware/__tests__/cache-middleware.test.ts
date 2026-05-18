import { describe, it, expect } from "vitest";
import { buildCacheKey } from "../cache-middleware.js";

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
});
