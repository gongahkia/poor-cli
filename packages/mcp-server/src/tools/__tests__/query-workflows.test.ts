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

vi.mock("../../apis/lta/client.js", () => ({
  getBusArrivals: vi.fn(),
  getTrainAlerts: vi.fn(),
  getTrafficIncidents: vi.fn(),
}));

vi.mock("../../apis/nea/client.js", () => ({
  getForecast2Hr: vi.fn(),
  getAirQuality: vi.fn(),
  getRainfall: vi.fn(),
}));

vi.mock("../../apis/cea/client.js", () => ({
  getCeaSalespersons: vi.fn(),
}));

vi.mock("../../apis/bca/client.js", () => ({
  getBcaLicensedBuilders: vi.fn(),
  getBcaRegisteredContractors: vi.fn(),
}));

vi.mock("../../apis/acra/client.js", () => ({
  getAcraEntities: vi.fn(),
}));

import { query as masQuery } from "../../apis/mas/client.js";
import { geocode, getPopulationData } from "../../apis/onemap/client.js";
import { uraFetch } from "../../apis/ura/client.js";
import { getDataset, searchDatasets as datagovSearch } from "../../apis/datagov/client.js";
import { getTrainAlerts, getTrafficIncidents } from "../../apis/lta/client.js";
import { getAirQuality, getForecast2Hr, getRainfall } from "../../apis/nea/client.js";
import { getCeaSalespersons } from "../../apis/cea/client.js";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../../apis/bca/client.js";
import { getAcraEntities } from "../../apis/acra/client.js";
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
    vi.mocked(getTrainAlerts).mockReset();
    vi.mocked(getTrafficIncidents).mockReset();
    vi.mocked(getForecast2Hr).mockReset();
    vi.mocked(getAirQuality).mockReset();
    vi.mocked(getRainfall).mockReset();
    vi.mocked(getCeaSalespersons).mockReset();
    vi.mocked(getBcaLicensedBuilders).mockReset();
    vi.mocked(getBcaRegisteredContractors).mockReset();
    vi.mocked(getAcraEntities).mockReset();
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
      workflow: "macro_brief",
      toolsUsed: ["sg_macro_brief"],
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

  it("routes broad transport status queries to the transport brief", async () => {
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [{ line: "NSL" }],
      messages: [{ content: "Minor delay", createdDate: "2026-03-26T08:00:00+08:00" }],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([
      { type: "Road Works" },
    ] as never);

    const result = await runQuery({
      query: "Transport status in Singapore right now",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "transport_brief",
      toolsUsed: ["sg_transport_brief"],
    });
  });

  it("routes broad environment snapshot queries to the environment brief", async () => {
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Tampines",
        forecast: "Partly Cloudy",
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getAirQuality).mockResolvedValue([
      {
        region: "East",
        psi24h: 40,
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getRainfall).mockResolvedValue([
      {
        stationId: "S107",
        stationName: "Tampines",
        value: 0.2,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const result = await runQuery({
      query: "Environment snapshot of Singapore right now",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "environment_brief",
      toolsUsed: ["sg_environment_brief"],
    });
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

  it("rejects csv output for multi-step workflows with a clear limitation message", async () => {
    const result = await runQuery({
      query: "Give me a macro snapshot of Singapore",
      mode: "execute",
      format: "csv",
    });

    expect(result.isError).toBe(true);
    expect(result.structuredContent).toMatchObject({
      status: "unsupported",
      workflow: "macro_brief",
    });
    expect(JSON.stringify(result.structuredContent)).toContain("only supports markdown or json");
  });

  it("renders single-step geocode queries in json when requested", async () => {
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

    const result = await runQuery({
      query: "Find 168742",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    const text = result.content.find((item) => item.type === "text")?.text;
    expect(text).toBeDefined();
    expect(JSON.parse(text!)).toMatchObject([
      {
        postal: "168742",
        lat: 1.3001,
        lng: 103.8392,
      },
    ]);
  });

  it("executes the business registry diligence workflow for a named company", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        uen: "201912345K",
        issuanceAgencyId: "ACRA",
        entityName: "ABC CONSTRUCTION PTE LTD",
        entityTypeDescription: "Local Company",
        businessConstitutionDescription: null,
        companyTypeDescription: "Private Company Limited by Shares",
        pafConstitutionDescription: null,
        entityStatusDescription: "Live Company",
        registrationIncorporationDate: "2019-04-01",
        uenIssueDate: "2019-04-01",
        addressType: "LOCAL",
        block: "1",
        streetName: "MAIN STREET",
        levelNo: "02",
        unitNo: "01",
        buildingName: "ABC BUILDING",
        postalCode: "123456",
        otherAddressLine1: null,
        otherAddressLine2: null,
        accountDueDate: "2026-04-01",
        annualReturnDate: "2025-04-01",
        primarySsicCode: "41001",
        primarySsicDescription: "GENERAL CONTRACTORS",
        primaryUserDescribedActivity: null,
        secondarySsicCode: null,
        secondarySsicDescription: null,
        secondaryUserDescribedActivity: null,
        noOfOfficers: 3,
      },
    ]);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([
      {
        companyName: "ABC CONSTRUCTION PTE LTD",
        uenNo: "201912345K",
        className: "General Builder Class 1",
        classCode: "GB1",
        additionalInfo: null,
        expiryDate: "2026-12-31",
        buildingNo: "1",
        streetName: "MAIN STREET",
        unitNo: null,
        buildingName: null,
        postalCode: "123456",
        telNo: "61234567",
      },
    ]);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([
      {
        companyName: "ABC CONSTRUCTION PTE LTD",
        uenNo: "201912345K",
        workhead: "CW01",
        grade: "C3",
        additionalInfo: "CRS",
        expiryDate: "2026-12-31",
        buildingNo: null,
        streetName: "MAIN STREET",
        unitNo: null,
        buildingName: null,
        postalCode: "123456",
        telNo: "61234567",
      },
    ]);

    const result = await runQuery({
      query: "Run registry diligence for company ABC CONSTRUCTION PTE LTD workhead CW01",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "business_dossier",
      toolsUsed: ["sg_business_dossier"],
    });
    expect(vi.mocked(getAcraEntities)).toHaveBeenCalledWith(
      expect.objectContaining({
        entityName: "ABC CONSTRUCTION PTE LTD",
        limit: 5,
      }),
    );
    expect(vi.mocked(getBcaRegisteredContractors)).toHaveBeenCalledWith(
      expect.objectContaining({
        companyName: "ABC CONSTRUCTION PTE LTD",
        workhead: "CW01",
        limit: 5,
      }),
    );
    expect(vi.mocked(getCeaSalespersons)).not.toHaveBeenCalled();
  });
});
