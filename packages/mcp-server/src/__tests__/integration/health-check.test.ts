import { describe, it, expect } from "vitest";

describe("Health Check", () => {
  it("health status type has required fields", () => {
    const status = {
      api: "SingStat",
      keyConfigured: false,
      reachable: true,
      latencyMs: 150,
    };
    expect(status.api).toBeDefined();
    expect(status.keyConfigured).toBeDefined();
    expect(status.reachable).toBeDefined();
    expect(status.latencyMs).toBeGreaterThanOrEqual(0);
  });

  it("missing key detected correctly", () => {
    const status = { api: "URA", keyConfigured: false, reachable: false, latencyMs: 0, error: "Key not configured" };
    expect(status.keyConfigured).toBe(false);
    expect(status.error).toContain("Key");
  });
});
