import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { Cache } from "../cache.js";

describe("Cache", () => {
  let cache: Cache;

  beforeEach(() => {
    cache = new Cache(":memory:");
  });

  afterEach(() => {
    cache.close();
  });

  it("set then get returns stored value", () => {
    cache.set("test:key", JSON.stringify({ value: 42 }), 300);
    const result = cache.get("test:key");
    expect(result).toBe(JSON.stringify({ value: 42 }));
  });

  it("returns null after TTL expiry", () => {
    cache.set("test:key", "value", 0);
    const result = cache.get("test:key");
    expect(result).toBeNull();
  });

  it("returns null for missing keys", () => {
    const result = cache.get("nonexistent");
    expect(result).toBeNull();
  });

  it("invalidate by pattern deletes matching keys only", () => {
    cache.set("singstat:search:abc", "1", 300);
    cache.set("singstat:table:def", "2", 300);
    cache.set("mas:rates:ghi", "3", 300);

    const deleted = cache.invalidate("singstat:%");
    expect(deleted).toBe(2);
    expect(cache.get("mas:rates:ghi")).toBe("3");
  });

  it("stats tracks hits and misses", () => {
    cache.set("key", "value", 300);
    cache.get("key"); // hit
    cache.get("key"); // hit
    cache.get("missing"); // miss

    const stats = cache.stats();
    expect(stats.hits).toBe(2);
    expect(stats.misses).toBe(1);
    expect(stats.entries).toBe(1);
  });

  it("handles large values", () => {
    const largeValue = "x".repeat(2_000_000);
    cache.set("large", largeValue, 300);
    expect(cache.get("large")).toBe(largeValue);
  });

  it("clear removes all entries", () => {
    cache.set("a", "1", 300);
    cache.set("b", "2", 300);
    cache.clear();
    expect(cache.get("a")).toBeNull();
    expect(cache.get("b")).toBeNull();
    expect(cache.stats().entries).toBe(0);
  });

  it("upsert replaces existing value", () => {
    cache.set("key", "old", 300);
    cache.set("key", "new", 300);
    expect(cache.get("key")).toBe("new");
  });
});
