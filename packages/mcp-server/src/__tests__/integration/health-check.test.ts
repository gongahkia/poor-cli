import { afterEach, describe, expect, it, vi } from "vitest";
import {
  checkApiHealth,
  getHealthCheckTargets,
  getLtaCredentialSource,
  hasLtaKey,
  hasOneMapCredentials,
  hasUraKey,
  healthCheckToolDefinitions,
} from "../../tools/health-check.js";

const createLookup = (values: Readonly<Record<string, string>>) => ({
  getKey: (key: string) => values[key] ?? null,
});

afterEach(() => {
  delete process.env["SG_API_ONEMAP_EMAIL"];
  delete process.env["SG_API_ONEMAP_PASSWORD"];
  delete process.env["SG_API_URA_KEY"];
  delete process.env["SG_API_LTA_KEY"];
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

  it("detects LTA key from configured credentials", () => {
    expect(hasLtaKey(createLookup({}))).toBe(false);
    expect(hasLtaKey(createLookup({ lta: "lta-secret" }))).toBe(true);
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
        credentialSource: () => "none",
      },
      fetchFn,
      createLookup({}),
    );

    expect(status.reachable).toBe(true);
    expect(status.configured).toBe(false);
    expect(status.credentialSource).toBe("none");
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
        credentialSource: () => "not_required",
      },
      fetchFn,
      createLookup({}),
    );

    expect(status.reachable).toBe(false);
    expect(status.credentialSource).toBe("not_required");
    expect(status.error).toContain("network down");
  });

  it("includes NEA in the public health-check targets", () => {
    expect(getHealthCheckTargets()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ api: "NEA", authRequired: false }),
      ]),
    );
  });

  it("reports mixed credential sources when env and keystore are both present", () => {
    process.env["SG_API_LTA_KEY"] = "lta-env";

    expect(getLtaCredentialSource(createLookup({ lta: "lta-keystore" }))).toBe("mixed");
  });

  it("returns structured health-check records with dependency coverage notes", async () => {
    const definition = healthCheckToolDefinitions.find((tool) => tool.name === "sg_health_check");
    if (definition === undefined) {
      throw new Error("sg_health_check definition not found");
    }

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    const originalFetch = globalThis.fetch;
    vi.stubGlobal("fetch", fetchMock);

    try {
      const result = await definition.handler({});
      const records = result.structuredContent?.["records"];

      expect(result.isError).toBeUndefined();
      expect(Array.isArray(records)).toBe(true);
      expect(records).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            api: "data.gov.sg",
            credentialSource: "not_required",
            dependentFamilies: expect.arrayContaining(["HDB", "CEA", "BCA", "ACRA"]),
            coverageNotes: expect.arrayContaining([
              expect.stringContaining("curated registry"),
            ]),
          }),
        ]),
      );
    } finally {
      vi.stubGlobal("fetch", originalFetch);
    }
  });
});
