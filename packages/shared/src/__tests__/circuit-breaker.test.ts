import { describe, it, expect, vi } from "vitest";
import { CircuitBreaker } from "../circuit-breaker.js";

describe("CircuitBreaker", () => {
  it("starts in CLOSED state", () => {
    const breaker = new CircuitBreaker("test");
    expect(breaker.getState()).toBe("CLOSED");
  });

  it("stays CLOSED on success", async () => {
    const breaker = new CircuitBreaker("test", 3, 100);
    await breaker.execute(() => Promise.resolve("ok"));
    expect(breaker.getState()).toBe("CLOSED");
  });

  it("opens after reaching failure threshold", async () => {
    const breaker = new CircuitBreaker("test", 3, 100);
    const fail = () => Promise.reject(new Error("fail"));
    for (let i = 0; i < 3; i++) {
      await breaker.execute(fail).catch(() => {});
    }
    expect(breaker.getState()).toBe("OPEN");
  });

  it("rejects immediately when OPEN", async () => {
    const breaker = new CircuitBreaker("test", 1, 60000);
    await breaker.execute(() => Promise.reject(new Error("fail"))).catch(() => {});
    expect(breaker.getState()).toBe("OPEN");
    await expect(breaker.execute(() => Promise.resolve("ok"))).rejects.toThrow("Circuit breaker OPEN");
  });

  it("transitions to HALF_OPEN after reset timeout", async () => {
    vi.useFakeTimers();
    const breaker = new CircuitBreaker("test", 1, 200);
    await breaker.execute(() => Promise.reject(new Error("fail"))).catch(() => {});
    expect(breaker.getState()).toBe("OPEN");
    vi.advanceTimersByTime(200);
    // next call should attempt (half-open probe)
    await breaker.execute(() => Promise.resolve("recovered"));
    expect(breaker.getState()).toBe("CLOSED");
    vi.useRealTimers();
  });

  it("re-opens on failure during HALF_OPEN", async () => {
    vi.useFakeTimers();
    const breaker = new CircuitBreaker("test", 1, 200);
    await breaker.execute(() => Promise.reject(new Error("fail"))).catch(() => {});
    expect(breaker.getState()).toBe("OPEN");
    vi.advanceTimersByTime(200);
    await breaker.execute(() => Promise.reject(new Error("still failing"))).catch(() => {});
    expect(breaker.getState()).toBe("OPEN");
    vi.useRealTimers();
  });

  it("resets failure count on successful HALF_OPEN probe", async () => {
    vi.useFakeTimers();
    const breaker = new CircuitBreaker("test", 2, 100);
    await breaker.execute(() => Promise.reject(new Error("1"))).catch(() => {});
    await breaker.execute(() => Promise.reject(new Error("2"))).catch(() => {});
    expect(breaker.getState()).toBe("OPEN");
    vi.advanceTimersByTime(100);
    await breaker.execute(() => Promise.resolve("ok"));
    expect(breaker.getState()).toBe("CLOSED");
    // should tolerate one failure without opening again (threshold=2)
    await breaker.execute(() => Promise.reject(new Error("3"))).catch(() => {});
    expect(breaker.getState()).toBe("CLOSED");
    vi.useRealTimers();
  });
});
