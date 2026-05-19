import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/acra/client.js", () => ({
  getAcraEntities: vi.fn().mockResolvedValue([{ entityName: "DP ARCHITECTS PTE LTD", uen: "199100765E" }]),
}));

vi.mock("../../apis/boa/client.js", () => ({
  getBoaArchitectureFirms: vi.fn().mockResolvedValue([{ firmName: "DP ARCHITECTS PTE LTD" }]),
}));

import { getAcraEntities } from "../../apis/acra/client.js";
import { getBoaArchitectureFirms } from "../../apis/boa/client.js";
import {
  checkApiHealth,
  getHealthCheckTargets,
  healthCheckToolDefinitions,
  probeDatagovDatastoreHealth,
  probeDatagovFileDownloadHealth,
  probeExternalDiligenceHealth,
} from "../../tools/health-check.js";

const createLookup = (values: Readonly<Record<string, string>>) => ({
  getKey: (key: string) => values[key] ?? null,
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("Health Check", () => {
  it("treats HTTP errors as reachable services", async () => {
    const status = await checkApiHealth(
      {
        api: "External Diligence",
        classification: "live_public",
        url: "https://example.test",
        probeMode: "runtime_client",
        representativeTool: "sg_sanctions_screen",
        releaseBlocking: false,
        authRequired: false,
        configured: () => true,
        credentialSource: () => "not_required",
        probe: vi.fn().mockResolvedValue({
          ok: false,
          status: 429,
          statusText: "Too Many Requests",
        }),
      },
      createLookup({}),
    );

    expect(status.reachable).toBe(true);
    expect(status.configured).toBe(true);
    expect(status.credentialSource).toBe("not_required");
    expect(status.error).toContain("HTTP 429");
  });

  it("treats thrown fetch errors as unreachable", async () => {
    const status = await checkApiHealth(
      {
        api: "data.gov.sg datastore",
        classification: "shared_datagov_datastore",
        url: "https://example.test",
        probeMode: "runtime_client",
        representativeTool: "sg_acra_entities",
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

  it("returns CDD-only health-check targets", () => {
    expect(getHealthCheckTargets()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ api: "data.gov.sg datastore", representativeTool: "sg_acra_entities" }),
        expect.objectContaining({ api: "data.gov.sg file downloads", representativeTool: "sg_boa_architecture_firms" }),
        expect.objectContaining({ api: "External Diligence", representativeTool: "sg_sanctions_screen" }),
      ]),
    );
    expect(getHealthCheckTargets().map((target) => target.api)).not.toEqual(
      expect.arrayContaining(["SingStat", "MAS", "OneMap", "URA", "LTA DataMall", "NEA"]),
    );
  });

  it("uses retained CDD runtime clients for health probes", async () => {
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
    await expect(probeExternalDiligenceHealth()).resolves.toEqual({
      ok: true,
      status: 200,
      statusText: "OK",
    });

    expect(vi.mocked(getAcraEntities)).toHaveBeenCalledWith({ entityName: "DP ARCHITECTS PTE LTD", limit: 1 });
    expect(vi.mocked(getBoaArchitectureFirms)).toHaveBeenCalledWith({ limit: 1 });
  });

  it("returns structured CDD health-check records with dependency coverage notes", async () => {
    const definition = healthCheckToolDefinitions.find((tool) => tool.name === "sg_health_check");
    if (definition === undefined) {
      throw new Error("sg_health_check definition not found");
    }

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
          dependentFamilies: expect.arrayContaining(["ACRA", "BCA", "CEA", "GeBIZ"]),
          representativeTool: "sg_acra_entities",
          releaseBlocking: true,
        }),
        expect.objectContaining({
          api: "data.gov.sg file downloads",
          classification: "shared_file_download",
          credentialSource: "not_required",
          dependentFamilies: expect.arrayContaining(["BOA", "HSA", "HLB"]),
          representativeTool: "sg_boa_architecture_firms",
          releaseBlocking: true,
        }),
      ]),
    );
  });
});
