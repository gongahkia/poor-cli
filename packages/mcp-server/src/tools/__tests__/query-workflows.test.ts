import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/singstat/client.js", () => ({
  searchDatasets: vi.fn(),
  getTableData: vi.fn(),
  getTimeSeries: vi.fn(),
}));

vi.mock("../../apis/mas/client.js", () => ({
  query: vi.fn(),
}));

vi.mock("../../apis/onemap/client.js", () => ({
  geocode: vi.fn(),
  reverseGeocode: vi.fn(),
  getRoute: vi.fn(),
  getPopulationData: vi.fn(),
  convertSVY21toWGS84: vi.fn(),
  convertWGS84toSVY21: vi.fn(),
}));

vi.mock("../../apis/ura/client.js", () => ({
  getPropertyTransactions: vi.fn(),
  uraFetch: vi.fn(),
}));

vi.mock("../../apis/datagov/client.js", () => ({
  searchDatasets: vi.fn(),
  getDataset: vi.fn(),
  listCollections: vi.fn(),
}));

import { query as masQuery } from "../../apis/mas/client.js";
import { geocode, getPopulationData } from "../../apis/onemap/client.js";
import { uraFetch } from "../../apis/ura/client.js";
import { getDataset, searchDatasets as datagovSearch } from "../../apis/datagov/client.js";
import { queryToolDefinitions } from "../query-tool.js";

const runQuery = async (input: Readonly<Record<string, unknown>>) => {
  const definition = queryToolDefinitions.find((tool) => tool.name === "sg_query");
  if (definition === undefined) {
    throw new Error("sg_query definition not found");
  }
  return definition.handler(input);
};

describe("sg_query workflows", () => {
  beforeEach(() => {
    vi.mocked(masQuery).mockReset();
    vi.mocked(geocode).mockReset();
    vi.mocked(getPopulationData).mockReset();
    vi.mocked(uraFetch).mockReset();
    vi.mocked(datagovSearch).mockReset();
    vi.mocked(getDataset).mockReset();
  });

  it("returns a macro workflow plan without executing steps", async () => {
    const result = await runQuery({
      query: "Give me a macro snapshot of Singapore",
      mode: "plan",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "planned",
      mode: "plan",
      workflow: "macro_snapshot",
      toolsUsed: [
        "sg_singstat_search",
        "sg_singstat_search",
        "sg_mas_exchange_rates",
        "sg_mas_interest_rates",
      ],
    });
    expect(vi.mocked(masQuery)).not.toHaveBeenCalled();
  });

  it("executes a demographic profile workflow from a postal code", async () => {
    vi.mocked(geocode).mockResolvedValue([
      {
        address: "1 ORCHARD ROAD",
        building: "TEST",
        postal: "168742",
        lat: 1.3001,
        lng: 103.8392,
        x: 0,
        y: 0,
      },
    ]);
    vi.mocked(uraFetch).mockResolvedValue({
      Status: "OK",
      Result: [{ pln_area_n: "ORCHARD", region: "Central Region" }],
    });
    vi.mocked(getPopulationData)
      .mockResolvedValueOnce({
        planningArea: "ORCHARD",
        year: "2020",
        data: [{ age_group: "25-29", total: "1500" }],
      })
      .mockResolvedValueOnce({
        planningArea: "ORCHARD",
        year: "2020",
        data: [{ income_bracket: "$8k-$9k", total: "200" }],
      });

    const result = await runQuery({
      query: "Demographic profile for postal code 168742",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "demographic_profile",
    });
    expect(result.structuredContent?.["steps"]).toHaveLength(4);
    expect(vi.mocked(getPopulationData)).toHaveBeenCalledTimes(2);
  });

  it("executes dataset discovery and follows up with metadata on the top match", async () => {
    vi.mocked(datagovSearch).mockResolvedValue([
      {
        datasetId: "hawker-centres",
        name: "Hawker Centres",
        description: "Locations of hawker centres",
        managedByAgencyName: "NEA",
        format: "CSV",
        lastUpdatedAt: "2026-03-01",
        createdAt: "2020-01-01",
        status: "active",
      },
    ]);
    vi.mocked(getDataset).mockResolvedValue({
      datasetId: "hawker-centres",
      name: "Hawker Centres",
      description: "Locations of hawker centres",
      managedByAgencyName: "NEA",
      format: "CSV",
      lastUpdatedAt: "2026-03-01",
      createdAt: "2020-01-01",
      status: "active",
    });

    const result = await runQuery({
      query: "Find datasets about hawker centres",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "dataset_discovery",
    });
    expect(vi.mocked(getDataset)).toHaveBeenCalledWith("hawker-centres");
  });

  it("reports the failing step and suggested action when a workflow dependency cannot be resolved", async () => {
    vi.mocked(datagovSearch).mockResolvedValue([]);

    const result = await runQuery({
      query: "Find datasets about a definitely unknown topic",
      mode: "execute",
    });

    expect(result.isError).toBe(true);
    expect(result.structuredContent).toMatchObject({
      status: "failed",
      workflow: "dataset_discovery",
      failedStep: {
        tool: "sg_datagov_get",
        status: "failed",
      },
    });
    expect(JSON.stringify(result.structuredContent)).toContain("Broaden the dataset search terms");
  });
});
