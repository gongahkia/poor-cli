import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/onemap/client.js", () => ({
  geocode: vi.fn().mockResolvedValue([
    {
      address: "Fullerton Road",
      building: "Fullerton",
      postal: "049178",
      lat: 1.2864,
      lng: 103.8537,
      x: 0,
      y: 0,
    },
  ]),
}));

vi.mock("../../apis/ura/client.js", () => ({
  uraFetch: vi.fn().mockResolvedValue({
    Status: "Success",
    Result: [],
  }),
}));

vi.mock("../../apis/lta/client.js", () => ({
  getBusArrivals: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../apis/mas/client.js", () => ({
  query: vi.fn().mockResolvedValue([{ end_of_day: "2026-03-26", sora: 2.5 }]),
}));

vi.mock("../../apis/nea/client.js", () => ({
  getForecast2Hr: vi.fn().mockResolvedValue([{ area: "Tampines", forecast: "Fair", updatedAt: "2026-03-28T00:00:00Z" }]),
}));

vi.mock("../../apis/singstat/client.js", () => ({
  getTableData: vi.fn().mockResolvedValue({
    rows: [{ period: "2025 4Q", variable: "GDP At Current Market Prices", value: 156000, unit: "million" }],
    metadata: {
      title: "Gross Domestic Product",
      frequency: "Quarterly",
      source: "SingStat",
      lastUpdated: "2026-03-01",
    },
    total: 1,
  }),
}));

vi.mock("../../apis/hdb/client.js", () => ({
  getHdbResalePrices: vi.fn().mockResolvedValue([{ town: "Bedok", flatType: "4 ROOM", resalePrice: 500000 }]),
}));

vi.mock("../../apis/boa/client.js", () => ({
  getBoaArchitectureFirms: vi.fn().mockResolvedValue([{ firmName: "DP ARCHITECTS PTE LTD" }]),
}));

import { getBusArrivals } from "../../apis/lta/client.js";
import { query as queryMas } from "../../apis/mas/client.js";
import { getForecast2Hr } from "../../apis/nea/client.js";
import { geocode } from "../../apis/onemap/client.js";
import { getTableData as getSingStatTableData } from "../../apis/singstat/client.js";
import { getHdbResalePrices } from "../../apis/hdb/client.js";
import { getBoaArchitectureFirms } from "../../apis/boa/client.js";
import { uraFetch } from "../../apis/ura/client.js";
import {
  checkApiHealth,
  getHealthCheckTargets,
  getLtaCredentialSource,
  hasLtaKey,
  hasOneMapCredentials,
  hasUraKey,
  healthCheckToolDefinitions,
  probeDatagovDatastoreHealth,
  probeDatagovFileDownloadHealth,
  probeLtaHealth,
  probeMasHealth,
  probeNeaHealth,
  probeOneMapHealth,
  probeSingStatHealth,
  probeUraHealth,
} from "../../tools/health-check.js";

const createLookup = (values: Readonly<Record<string, string>>) => ({
  getKey: (key: string) => values[key] ?? null,
});

afterEach(() => {
  delete process.env["SG_API_ONEMAP_EMAIL"];
  delete process.env["SG_API_ONEMAP_PASSWORD"];
  delete process.env["SG_API_URA_KEY"];
  delete process.env["SG_API_LTA_KEY"];
  vi.clearAllMocks();
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
    const status = await checkApiHealth(
      {
        api: "URA",
        classification: "live_authenticated",
        url: "https://example.test",
        probeMode: "runtime_client",
        representativeTool: "sg_ura_dev_charges",
        releaseBlocking: true,
        authRequired: true,
        configured: () => false,
        credentialSource: () => "none",
        probe: vi.fn().mockResolvedValue({
          ok: false,
          status: 401,
          statusText: "Unauthorized",
        }),
      },
      createLookup({}),
    );

    expect(status.reachable).toBe(true);
    expect(status.configured).toBe(false);
    expect(status.credentialSource).toBe("none");
    expect(status.error).toContain("HTTP 401");
  });

  it("treats thrown fetch errors as unreachable", async () => {
    const status = await checkApiHealth(
      {
        api: "SingStat",
        classification: "live_public",
        url: "https://example.test",
        probeMode: "runtime_client",
        representativeTool: "sg_singstat_table",
        releaseBlocking: true,
        authRequired: false,
        configured: () => true,
        credentialSource: () => "not_required",
        probe: vi.fn().mockRejectedValue(new Error("network down")),
      },
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

  it("uses the live runtime clients for health probes", async () => {
    await expect(probeSingStatHealth()).resolves.toEqual({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    await expect(probeMasHealth()).resolves.toEqual({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    await expect(probeOneMapHealth()).resolves.toEqual({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    await expect(probeUraHealth()).resolves.toEqual({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    await expect(probeLtaHealth()).resolves.toEqual({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    await expect(probeDatagovDatastoreHealth()).resolves.toEqual({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    await expect(probeDatagovFileDownloadHealth()).resolves.toEqual({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    await expect(probeNeaHealth()).resolves.toEqual({
      ok: true,
      status: 200,
      statusText: "OK",
    });

    expect(vi.mocked(getSingStatTableData)).toHaveBeenCalledWith("M015631", {
      variables: ["GDP At Current Market Prices"],
    });
    expect(vi.mocked(queryMas)).toHaveBeenCalledWith("interest_rates_sora", { limit: 1 });
    expect(vi.mocked(geocode)).toHaveBeenCalledWith("049178", 1);
    expect(vi.mocked(uraFetch)).toHaveBeenCalledWith("DC_Rates");
    expect(vi.mocked(getBusArrivals)).toHaveBeenCalledWith("83139");
    expect(vi.mocked(getHdbResalePrices)).toHaveBeenCalledWith({ town: "Bedok", flatType: "4 ROOM", limit: 1 });
    expect(vi.mocked(getBoaArchitectureFirms)).toHaveBeenCalledWith({ limit: 1 });
    expect(vi.mocked(getForecast2Hr)).toHaveBeenCalledWith("Tampines");
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

    process.env["SG_API_ONEMAP_EMAIL"] = "user@example.com";
    process.env["SG_API_ONEMAP_PASSWORD"] = "secret";
    process.env["SG_API_URA_KEY"] = "ura-env";
    process.env["SG_API_LTA_KEY"] = "lta-env";

    const result = await definition.handler({});
    const records = result.structuredContent?.["records"];

    expect(result.isError).toBeUndefined();
    expect(Array.isArray(records)).toBe(true);
    expect(records).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          api: "data.gov.sg datastore",
          classification: "shared_datagov_datastore",
          credentialSource: "not_required",
          dependentFamilies: expect.arrayContaining(["HDB", "CEA", "BCA", "ACRA", "STB"]),
          representativeTool: "sg_hdb_resale_prices",
          releaseBlocking: true,
        }),
        expect.objectContaining({
          api: "data.gov.sg file downloads",
          classification: "shared_file_download",
          credentialSource: "not_required",
          dependentFamilies: expect.arrayContaining(["BOA", "HSA", "HLB", "PA"]),
          representativeTool: "sg_boa_architecture_firms",
          releaseBlocking: true,
        }),
        expect.objectContaining({
          api: "OneMap",
          configured: true,
          credentialSource: "env",
          reachable: true,
        }),
      ]),
    );
  });
});
