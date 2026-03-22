import { afterEach, describe, expect, it, vi } from "vitest";
import { checkApiHealth, hasOneMapCredentials, hasUraKey } from "../../tools/health-check.js";

const createLookup = (values: Readonly<Record<string, string>>) => ({
  getKey: (key: string) => values[key] ?? null,
});

afterEach(() => {
  delete process.env["SG_API_ONEMAP_EMAIL"];
  delete process.env["SG_API_ONEMAP_PASSWORD"];
  delete process.env["SG_API_URA_KEY"];
});

describe("Health Check", () => {
  it("requires both OneMap email and password", () => {
    expect(hasOneMapCredentials(createLookup({ onemap_email: "user@example.com" }))).toBe(false);
    expect(
      hasOneMapCredentials(
        createLookup({
          onemap_email: "user@example.com",
          onemap_password: "secret",
        }),
      ),
    ).toBe(true);
  });

  it("detects URA key from configured credentials", () => {
    expect(hasUraKey(createLookup({}))).toBe(false);
    expect(hasUraKey(createLookup({ ura: "ura-secret" }))).toBe(true);
  });

  it("treats HTTP errors as reachable services", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
    });

    const status = await checkApiHealth(
      {
        api: "URA",
        url: "https://example.test",
        authRequired: true,
        configured: () => false,
      },
      fetchFn,
      createLookup({}),
    );

    expect(status.reachable).toBe(true);
    expect(status.configured).toBe(false);
    expect(status.error).toContain("HTTP 401");
  });

  it("treats thrown fetch errors as unreachable", async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error("network down"));

    const status = await checkApiHealth(
      {
        api: "SingStat",
        url: "https://example.test",
        authRequired: false,
        configured: () => true,
      },
      fetchFn,
      createLookup({}),
    );

    expect(status.reachable).toBe(false);
    expect(status.error).toContain("network down");
  });
});
