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

vi.mock("../../apis/boa/client.js", () => ({
  getBoaArchitects: vi.fn(),
  getBoaArchitectureFirms: vi.fn(),
}));

vi.mock("../../apis/acra/client.js", () => ({
  getAcraEntities: vi.fn(),
}));

vi.mock("../../apis/gebiz/client.js", () => ({
  getGeBIZTenders: vi.fn(),
}));

vi.mock("../../apis/hlb/client.js", () => ({
  getHlbHotels: vi.fn(),
}));

vi.mock("../../apis/hsa/client.js", () => ({
  getHsaHealthProductLicensees: vi.fn(),
  getHsaLicensedPharmacies: vi.fn(),
}));

vi.mock("../../apis/pa/client.js", () => ({
  getPaCommunityOutlets: vi.fn(),
  getPaResidentNetworkCentres: vi.fn(),
}));

vi.mock("../../apis/sportsg/client.js", () => ({
  getSportSgFacilities: vi.fn(),
}));

vi.mock("../../apis/ecda/client.js", () => ({
  getEcdaChildcareCentres: vi.fn(),
}));

vi.mock("../../apis/msf/client.js", () => ({
  getMsfFamilyServices: vi.fn(),
  getMsfStudentCareServices: vi.fn(),
  getMsfSocialServiceOffices: vi.fn(),
}));

vi.mock("../../apis/moe/client.js", () => ({
  getSchools: vi.fn(),
}));

vi.mock("../../apis/moh/client.js", () => ({
  getHealthcareFacilities: vi.fn(),
}));

import { query as masQuery } from "../../apis/mas/client.js";
import { geocode, getPopulationData, getRoute } from "../../apis/onemap/client.js";
import { searchDatasets as singstatSearch } from "../../apis/singstat/client.js";
import { uraFetch } from "../../apis/ura/client.js";
import {
  getDataset,
  listCollections,
  searchDatasets as datagovSearch,
} from "../../apis/datagov/client.js";
import { getTrainAlerts, getTrafficIncidents } from "../../apis/lta/client.js";
import { getAirQuality, getForecast2Hr, getRainfall } from "../../apis/nea/client.js";
import { getCeaSalespersons } from "../../apis/cea/client.js";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../../apis/bca/client.js";
import { getBoaArchitects, getBoaArchitectureFirms } from "../../apis/boa/client.js";
import { getAcraEntities } from "../../apis/acra/client.js";
import { getGeBIZTenders } from "../../apis/gebiz/client.js";
import { getHlbHotels } from "../../apis/hlb/client.js";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../../apis/hsa/client.js";
import { getPaCommunityOutlets, getPaResidentNetworkCentres } from "../../apis/pa/client.js";
import { getSportSgFacilities } from "../../apis/sportsg/client.js";
import { getEcdaChildcareCentres } from "../../apis/ecda/client.js";
import {
  getMsfFamilyServices,
  getMsfSocialServiceOffices,
  getMsfStudentCareServices,
} from "../../apis/msf/client.js";
import { getSchools } from "../../apis/moe/client.js";
import { getHealthcareFacilities } from "../../apis/moh/client.js";
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
    vi.mocked(singstatSearch).mockReset();
    vi.mocked(masQuery).mockReset();
    vi.mocked(geocode).mockReset();
    vi.mocked(getRoute).mockReset();
    vi.mocked(getPopulationData).mockReset();
    vi.mocked(uraFetch).mockReset();
    vi.mocked(datagovSearch).mockReset();
    vi.mocked(getDataset).mockReset();
    vi.mocked(listCollections).mockReset();
    vi.mocked(getTrainAlerts).mockReset();
    vi.mocked(getTrafficIncidents).mockReset();
    vi.mocked(getForecast2Hr).mockReset();
    vi.mocked(getAirQuality).mockReset();
    vi.mocked(getRainfall).mockReset();
    vi.mocked(getCeaSalespersons).mockReset();
    vi.mocked(getBcaLicensedBuilders).mockReset();
    vi.mocked(getBcaRegisteredContractors).mockReset();
    vi.mocked(getBoaArchitects).mockReset();
    vi.mocked(getBoaArchitectureFirms).mockReset();
    vi.mocked(getAcraEntities).mockReset();
    vi.mocked(getGeBIZTenders).mockReset();
    vi.mocked(getHlbHotels).mockReset();
    vi.mocked(getHsaHealthProductLicensees).mockReset();
    vi.mocked(getHsaLicensedPharmacies).mockReset();
    vi.mocked(getPaCommunityOutlets).mockReset();
    vi.mocked(getPaResidentNetworkCentres).mockReset();
    vi.mocked(getSportSgFacilities).mockReset();
    vi.mocked(getEcdaChildcareCentres).mockReset();
    vi.mocked(getMsfFamilyServices).mockReset();
    vi.mocked(getMsfStudentCareServices).mockReset();
    vi.mocked(getMsfSocialServiceOffices).mockReset();
    vi.mocked(getSchools).mockReset();
    vi.mocked(getHealthcareFacilities).mockReset();
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

  it("returns optional context IDs when requested", async () => {
    const result = await runQuery({
      query: "Give me a macro snapshot of Singapore",
      mode: "plan",
      includeContextIds: true,
    });

    expect(result.structuredContent).toMatchObject({
      status: "planned",
      contextIds: {
        traceId: expect.stringMatching(
          /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
        ),
        requestId: expect.stringMatching(
          /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
        ),
      },
    });
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

  it("executes a route workflow from two Singapore postal codes", async () => {
    vi.mocked(geocode)
      .mockResolvedValueOnce([
        {
          address: "5 RAFFLES PLACE",
          building: "RAFFLES PLACE MRT STATION",
          postal: "048618",
          lat: 1.28413,
          lng: 103.85146,
          x: 0,
          y: 0,
        },
        {
          address: "1 FULLERTON SQUARE",
          building: "FULLERTON",
          postal: "049178",
          lat: 1.2864,
          lng: 103.8537,
          x: 0,
          y: 0,
        },
      ])
      .mockResolvedValueOnce([
        {
          address: "5 RAFFLES PLACE",
          building: "RAFFLES PLACE MRT STATION",
          postal: "048618",
          lat: 1.28413,
          lng: 103.85146,
          x: 0,
          y: 0,
        },
        {
          address: "1 RAFFLES PLACE",
          building: "ONE RAFFLES PLACE",
          postal: "048616",
          lat: 1.284,
          lng: 103.851,
          x: 0,
          y: 0,
        },
      ]);
    vi.mocked(getRoute).mockResolvedValue({
      totalDistance: 650,
      totalTime: 540,
      instructions: [
        { instruction: "Walk straight", road: "Fullerton Road", distance: 300 },
      ],
      routeGeometry: [],
    } as never);

    const result = await runQuery({
      query: "Walk from 049178 to 048616",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "route_plan",
    });
    expect(result.structuredContent?.["resultSummary"]).toBeUndefined();
    expect(result.structuredContent?.["nextActions"]).toBeUndefined();
    const text = result.content.find((item) => item.type === "text")?.text;
    expect(JSON.parse(text!)).not.toHaveProperty("resultSummary");
    expect(JSON.parse(text!)).not.toHaveProperty("nextActions");
    expect(vi.mocked(getRoute)).toHaveBeenCalledWith(1.2864, 103.8537, 1.284, 103.851, "walk");
  });

  it("executes direct data.gov collection browsing through sg_query", async () => {
    vi.mocked(listCollections).mockResolvedValue([
      { collectionId: "housing", name: "Housing", datasetCount: 12 },
    ] as never);

    const result = await runQuery({
      query: "Browse data.gov collections",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "direct_tool",
      toolsUsed: ["sg_datagov_browse"],
    });
  });

  it("executes direct SingStat category browsing through sg_query", async () => {
    vi.mocked(singstatSearch).mockResolvedValue([
      {
        id: "M650151",
        title: "Transport Indicators",
        theme: "Transport",
        subject: "Transport",
        topic: "Transport",
        frequency: "Annual",
      },
    ]);

    const result = await runQuery({
      query: "Browse SingStat transport datasets",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "direct_tool",
      toolsUsed: ["sg_singstat_browse"],
    });
  });

  it("executes direct MOE school directory lookups through sg_query", async () => {
    vi.mocked(getSchools).mockResolvedValue([
      {
        name: "West Grove Primary School",
        level: "PRIMARY",
        zone: "WEST",
        address: "1 WEST ROAD",
        postalCode: "640001",
        telephone: "61234567",
        nature: "Government",
        type: "Co-Ed",
        url: "https://example.edu.sg",
      },
    ] as never);

    const result = await runQuery({
      query: "Find MOE primary schools in west zone",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "direct_tool",
      toolsUsed: ["sg_moe_schools"],
    });
    expect(vi.mocked(getSchools)).toHaveBeenCalledWith(
      expect.objectContaining({ level: "PRIMARY", zone: "WEST" }),
    );
  });

  it("executes direct MOH healthcare directory lookups through sg_query", async () => {
    vi.mocked(getHealthcareFacilities).mockResolvedValue([
      {
        name: "Singapore General Hospital",
        code: "HCI001",
        type: "HOSPITAL",
        street: "Outram Road",
        block: "1",
        postalCode: "169608",
        telephone: "62223333",
      },
    ] as never);

    const result = await runQuery({
      query: "Find MOH hospitals near postal code 119077",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "direct_tool",
      toolsUsed: ["sg_moh_facilities"],
    });
    expect(vi.mocked(getHealthcareFacilities)).toHaveBeenCalledWith(
      expect.objectContaining({ type: "HOSPITAL", postalCode: "119077" }),
    );
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
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "transport_brief",
      toolsUsed: ["sg_transport_brief"],
      resultSummary: {
        level: "disrupted",
      },
    });
    expect(Array.isArray(result.structuredContent?.["nextActions"])).toBe(true);
    const text = result.content.find((item) => item.type === "text")?.text;
    const payload = JSON.parse(text!);
    expect(payload.resultSummary).toMatchObject({ level: "disrupted" });
    expect(Array.isArray(payload.nextActions)).toBe(true);
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
      resultSummary: {
        level: "watch",
      },
    });
    expect(Array.isArray(result.structuredContent?.["nextActions"])).toBe(true);
    const text = result.content.find((item) => item.type === "text")?.text ?? "";
    expect(text).toContain("### Next Actions");
    expect(text).toContain("Ops result: watch");
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

    expect(result.isError).toBeUndefined();
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

  it("returns a clear blocker for reverse geocode prompts without coordinates", async () => {
    const result = await runQuery({
      query: "Reverse geocode this location",
      mode: "execute",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      workflow: "direct_tool",
      blockers: [
        expect.objectContaining({ field: "lat", directTool: "sg_onemap_reverse_geocode" }),
        expect.objectContaining({ field: "lng", directTool: "sg_onemap_reverse_geocode" }),
      ],
    });
    expect(JSON.stringify(result.structuredContent)).toContain("latitude and longitude");
  });

  it("returns a clear blocker for coordinate conversion prompts without a coordinate pair", async () => {
    const result = await runQuery({
      query: "Convert WGS84 to SVY21",
      mode: "execute",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      blockers: [
        expect.objectContaining({ field: "from", directTool: "sg_onemap_convert_coords" }),
        expect.objectContaining({ field: "x", directTool: "sg_onemap_convert_coords" }),
        expect.objectContaining({ field: "y", directTool: "sg_onemap_convert_coords" }),
      ],
    });
    expect(JSON.stringify(result.structuredContent)).toContain("source coordinate system");
  });

  it("returns a clear blocker for SingStat table requests without a table ID", async () => {
    const result = await runQuery({
      query: "Show me the SingStat table for GDP",
      mode: "execute",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      blockers: [expect.objectContaining({ field: "tableId", directTool: "sg_singstat_table" })],
    });
    expect(JSON.stringify(result.structuredContent)).toContain("SingStat table ID");
  });

  it("returns a blocked business-diligence response when no registry identifier is supplied", async () => {
    const result = await runQuery({
      query: "Run registry diligence for a company",
      mode: "execute",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      workflow: "business_dossier",
      blockers: expect.arrayContaining([
        expect.objectContaining({ field: "entityName", directTool: "sg_business_dossier" }),
        expect.objectContaining({ field: "uen", directTool: "sg_business_dossier" }),
        expect.objectContaining({ field: "registrationNo", directTool: "sg_cea_salespersons" }),
      ]),
    });
  });

  it("returns a blocked property-diligence response when no area hint is supplied", async () => {
    const result = await runQuery({
      query: "Property due diligence for an HDB resale",
      mode: "execute",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      workflow: "property_brief",
      blockers: expect.arrayContaining([
        expect.objectContaining({ field: "planningArea", directTool: "sg_property_brief" }),
        expect.objectContaining({ field: "postalCode", directTool: "sg_property_brief" }),
      ]),
    });
  });

  it("returns a blocked bus-arrivals response when no bus stop code is supplied", async () => {
    const result = await runQuery({
      query: "Bus arrivals right now",
      mode: "execute",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      workflow: "direct_tool",
      blockers: [expect.objectContaining({ field: "busStopCode", directTool: "sg_lta_bus_arrivals" })],
    });
  });

  it("returns a blocked data.gov resources response when the dataset id is missing", async () => {
    const result = await runQuery({
      query: "dataset resources",
      mode: "execute",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      blockers: [expect.objectContaining({ field: "datasetId", directTool: "sg_datagov_resources" })],
    });
  });

  it("returns a blocked data.gov rows response when the dataset id is missing", async () => {
    const result = await runQuery({
      query: "dataset rows",
      mode: "execute",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      blockers: [expect.objectContaining({ field: "datasetId", directTool: "sg_datagov_rows" })],
    });
  });

  it("executes civic discovery for a community club near a postal code", async () => {
    vi.mocked(geocode).mockResolvedValue([
      {
        address: "5 RAFFLES PLACE",
        building: "RAFFLES PLACE MRT STATION",
        postal: "048616",
        lat: 1.284,
        lng: 103.851,
        x: 0,
        y: 0,
      },
    ]);
    vi.mocked(getPaCommunityOutlets).mockResolvedValue([
      {
        name: "Downtown Community Club",
        category: "community",
        subcategory: "community_club",
        address: "5, Raffles Place",
        postalCode: "048616",
        lat: 1.284,
        lng: 103.85105,
        distanceKm: 0.006,
        sourceAgency: "People's Association",
        sourceDataset: "Community Club / PAssion WaVe Outlet",
        sourceUrl: "https://data.gov.sg/datasets/d_9de02d3fb33d96da1855f4fbef549a0f/view",
        lastUpdatedAt: "2024-04-17T18:17:50+08:00",
        type: "community_club",
        url: "https://www.onepa.gov.sg/cc",
      },
    ] as never);

    const result = await runQuery({
      query: "Find a community club near 048616",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "civic_discovery",
    });
    expect(vi.mocked(geocode)).toHaveBeenCalledWith("048616", undefined);
    expect(vi.mocked(getPaCommunityOutlets)).toHaveBeenCalledWith({
      type: "community_club",
      lat: 1.284,
      lng: 103.851,
      radiusKm: 3,
      format: "json",
    });
  });

  it("executes civic discovery for a SportSG facility from a planning area", async () => {
    vi.mocked(geocode).mockResolvedValue([
      {
        address: "BEDOK",
        building: "BEDOK",
        postal: "460000",
        lat: 1.324,
        lng: 103.93,
        x: 0,
        y: 0,
      },
    ]);
    vi.mocked(getSportSgFacilities).mockResolvedValue([
      {
        name: "Bedok Swimming Complex",
        category: "sports",
        subcategory: "swimming_complex",
        address: "1, Bedok North Street 1",
        postalCode: "460000",
        lat: 1.3238,
        lng: 103.9299,
        distanceKm: 0.032,
        sourceAgency: "Sport Singapore",
        sourceDataset: "SportSG Sport Facilities (GEOJSON)",
        sourceUrl: "https://data.gov.sg/datasets/d_9b87bab59d036a60fad2a91530e10773/view",
        lastUpdatedAt: "2024-04-17T18:17:50+08:00",
        facilityType: "swimming_complex",
        detailsUrl: "https://www.activesgcircle.gov.sg/facilities",
      },
    ] as never);

    const result = await runQuery({
      query: "Find a SportSG swimming complex near Bedok",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "civic_discovery",
    });
    expect(vi.mocked(geocode)).toHaveBeenCalledWith("Bedok", undefined);
    expect(vi.mocked(getSportSgFacilities)).toHaveBeenCalledWith({
      facilityType: "swimming_complex",
      lat: 1.324,
      lng: 103.93,
      radiusKm: 5,
      format: "json",
    });
  });

  it("executes civic discovery by exact childcare centre name without geocoding", async () => {
    vi.mocked(getEcdaChildcareCentres).mockResolvedValue([
      {
        name: "Little Seeds Preschool",
        category: "childcare",
        subcategory: "child care",
        address: "5 Raffles Place, #02-01",
        postalCode: null,
        lat: 1.28413,
        lng: 103.85146,
        sourceAgency: "Early Childhood Development Agency",
        sourceDataset: "Child Care Services + Listing of Centres",
        sourceUrl: "https://data.gov.sg/datasets/d_5d668e3f544335f8028f546827b773b4/view",
        lastUpdatedAt: "2026-03-19",
        centreCode: "CC0002",
        centreType: "CC",
        operatorType: "Little Seeds",
        serviceModel: "CHILD CARE",
        contactNo: "62345678",
        email: "hello@littleseeds.sg",
        website: "https://www.littleseeds.sg",
        hasVacancy: false,
        infantVacancyCurrentMonth: "full",
        playgroupVacancyCurrentMonth: "full",
        n1VacancyCurrentMonth: "full",
        n2VacancyCurrentMonth: "full",
        k1VacancyCurrentMonth: "full",
        k2VacancyCurrentMonth: "full",
      },
    ] as never);

    const result = await runQuery({
      query: "Find childcare centres named \"Little Seeds Preschool\"",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "civic_discovery",
    });
    expect(vi.mocked(geocode)).not.toHaveBeenCalled();
    expect(vi.mocked(getEcdaChildcareCentres)).toHaveBeenCalledWith({
      name: "Little Seeds Preschool",
      centreType: "CC",
      format: "json",
    });
  });

  it("returns a blocked civic-discovery response when the prompt says near me without a location", async () => {
    const result = await runQuery({
      query: "Find childcare centres near me",
      mode: "execute",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      workflow: "civic_discovery",
      blockers: expect.arrayContaining([
        expect.objectContaining({ field: "postalCode", directTool: "sg_onemap_geocode" }),
        expect.objectContaining({ field: "address", directTool: "sg_onemap_geocode" }),
        expect.objectContaining({ field: "name", directTool: "sg_ecda_childcare_centres" }),
      ]),
    });
    expect(vi.mocked(geocode)).not.toHaveBeenCalled();
    expect(vi.mocked(getEcdaChildcareCentres)).not.toHaveBeenCalled();
    expect(vi.mocked(getPaResidentNetworkCentres)).not.toHaveBeenCalled();
  });

  it("executes civic discovery for a family service centre near an address", async () => {
    vi.mocked(geocode).mockResolvedValue([
      {
        address: "BLK 230 ANG MO KIO AVE 3",
        building: "TEST",
        postal: "560230",
        lat: 1.3688544443488972,
        lng: 103.83789640387423,
        x: 0,
        y: 0,
      },
    ]);
    vi.mocked(getMsfFamilyServices).mockResolvedValue([
      {
        name: "Allkin Family Service Centre @ Ang Mo Kio 230",
        category: "social_support",
        subcategory: "family_service_centre",
        address: "Blk 230 Ang Mo Kio Ave 3 #01-1264",
        postalCode: "560230",
        lat: 1.3688544443488972,
        lng: 103.83789640387423,
        distanceKm: 0,
        sourceAgency: "Ministry of Social and Family Development",
        sourceDataset: "Family Services",
        sourceUrl: "https://data.gov.sg/datasets/d_add23c06f7267e799185c79ccaa2099b/view",
        lastUpdatedAt: "2025-12-03T18:52:26+08:00",
        description: "Family Service Centres",
        telephone: "6453 5349",
        email: "fscamk@allkin.org.sg",
        url: null,
      },
    ] as never);

    const result = await runQuery({
      query: "Find a family service centre near Blk 230 Ang Mo Kio Ave 3",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "civic_discovery",
    });
    expect(vi.mocked(geocode)).toHaveBeenCalledWith("Blk 230 Ang Mo Kio Ave 3", undefined);
    expect(vi.mocked(getMsfFamilyServices)).toHaveBeenCalledWith({
      lat: 1.3688544443488972,
      lng: 103.83789640387423,
      radiusKm: 3,
      format: "json",
    });
  });

  it("executes civic discovery for SCFA grade A student care from a planning area", async () => {
    vi.mocked(geocode).mockResolvedValue([
      {
        address: "TAMPINES",
        building: "TAMPINES",
        postal: "520000",
        lat: 1.3526,
        lng: 103.945,
        x: 0,
        y: 0,
      },
    ]);
    vi.mocked(getMsfStudentCareServices).mockResolvedValue([
      {
        name: "YMCA Student Care Centre @ Tampines",
        category: "childcare",
        subcategory: "student_care",
        address: "1 Tampines Street 11",
        postalCode: "521001",
        lat: 1.353,
        lng: 103.9448,
        distanceKm: 0.046,
        sourceAgency: "Ministry of Social and Family Development",
        sourceDataset: "Student Care Services",
        sourceUrl: "https://data.gov.sg/datasets/d_77e6e0d58ce4743dab1f26dfcbbeb6f4/view",
        lastUpdatedAt: "2026-02-23T12:48:33+08:00",
        auditStatus: "Grade A",
        auditDate: "2026-01-23",
        scfa: true,
        businessProfile: "Commercial Companies",
        monthlyFee: 295,
        enrolment: 100,
        telephone: "98375096",
        email: "cbscc@ymca.edu.sg",
      },
    ] as never);

    const result = await runQuery({
      query: "Find SCFA Grade A student care near Tampines",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "civic_discovery",
    });
    expect(vi.mocked(getMsfStudentCareServices)).toHaveBeenCalledWith({
      auditStatus: "Grade A",
      scfaOnly: true,
      lat: 1.3526,
      lng: 103.945,
      radiusKm: 5,
      format: "json",
    });
  });

  it("executes civic discovery for a social service office from coordinates", async () => {
    vi.mocked(getMsfSocialServiceOffices).mockResolvedValue([
      {
        name: "Social Service Office @ Queenstown",
        category: "social_support",
        subcategory: "social_service_office",
        address: "40, Margaret Drive, #02-01",
        postalCode: "140040",
        lat: 1.2964584179145409,
        lng: 103.80620757407047,
        distanceKm: 0.001,
        sourceAgency: "Ministry of Social and Family Development",
        sourceDataset: "Social Service Offices",
        sourceUrl: "https://data.gov.sg/datasets/d_22cfe2aed0bf20a679ab59bcaf0f8248/view",
        lastUpdatedAt: "2024-11-04T11:36:04+08:00",
        description: "Social Service Offices",
        url: null,
      },
    ] as never);

    const result = await runQuery({
      query: "Find a social service office near 1.29646, 103.80621",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "civic_discovery",
    });
    expect(vi.mocked(geocode)).not.toHaveBeenCalled();
    expect(vi.mocked(getMsfSocialServiceOffices)).toHaveBeenCalledWith({
      lat: 1.29646,
      lng: 103.80621,
      radiusKm: 3,
      format: "json",
    });
  });

  it("executes civic discovery by exact MSF office name without geocoding", async () => {
    vi.mocked(getMsfSocialServiceOffices).mockResolvedValue([
      {
        name: "Social Service Office @ Queenstown",
        category: "social_support",
        subcategory: "social_service_office",
        address: "40, Margaret Drive, #02-01",
        postalCode: "140040",
        lat: 1.2964584179145409,
        lng: 103.80620757407047,
        sourceAgency: "Ministry of Social and Family Development",
        sourceDataset: "Social Service Offices",
        sourceUrl: "https://data.gov.sg/datasets/d_22cfe2aed0bf20a679ab59bcaf0f8248/view",
        lastUpdatedAt: "2024-11-04T11:36:04+08:00",
        description: "Social Service Offices",
        url: null,
      },
    ] as never);

    const result = await runQuery({
      query: "Find a social service office named \"Social Service Office @ Queenstown\"",
      mode: "execute",
      format: "json",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "civic_discovery",
    });
    expect(vi.mocked(geocode)).not.toHaveBeenCalled();
    expect(vi.mocked(getMsfSocialServiceOffices)).toHaveBeenCalledWith({
      name: "Social Service Office @ Queenstown",
      format: "json",
    });
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

  it("executes the architecture-firm diligence workflow with explicit BOA scope", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "DESIGN LAB PTE LTD",
        uen: "202012345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getBoaArchitectureFirms).mockResolvedValue([
      {
        firmName: "DESIGN LAB PTE LTD",
        firmAddress: "1 MAIN STREET",
        firmPhone: "61234567",
        firmFax: null,
        firmEmail: "hello@designlab.sg",
      },
    ] as never);
    vi.mocked(getBoaArchitects).mockResolvedValue([] as never);

    const result = await runQuery({
      query: "Architecture firm diligence for company DESIGN LAB PTE LTD",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "architecture_firm_diligence",
      toolsUsed: ["sg_business_dossier"],
    });
    expect(vi.mocked(getBoaArchitectureFirms)).toHaveBeenCalledWith(
      expect.objectContaining({ firmName: "DESIGN LAB PTE LTD", limit: 5 }),
    );
    expect(vi.mocked(getGeBIZTenders)).not.toHaveBeenCalled();
  });

  it("extracts a clean entity name from the architecture-firm diligence prompt shape", async () => {
    vi.mocked(getBoaArchitectureFirms).mockResolvedValue([
      {
        firmName: "DP Architects",
        firmAddress: "6 RAFFLES BOULEVARD",
        firmPhone: "63372288",
        firmFax: null,
        firmEmail: "info@dpa.com.sg",
      },
    ] as never);
    vi.mocked(getBoaArchitects).mockResolvedValue([] as never);
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "DP Architects",
        uen: "199100765E",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getGeBIZTenders).mockResolvedValue([] as never);

    const result = await runQuery({
      query: "Architecture firm diligence for DP Architects",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "architecture_firm_diligence",
    });
    expect(vi.mocked(getBoaArchitectureFirms)).toHaveBeenCalledWith(
      expect.objectContaining({ firmName: "DP Architects", limit: 5 }),
    );
    expect(vi.mocked(getAcraEntities)).toHaveBeenCalledWith(
      expect.objectContaining({ entityName: "DP Architects", limit: 5 }),
    );
  });

  it("executes the healthcare supplier diligence workflow with HSA scope", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
        uen: "201012345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getHsaHealthProductLicensees).mockResolvedValue([
      {
        companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
        licenseType: "Controlled Drugs - Wholesale Licence",
        activityType: null,
        dosageForm: null,
        expiryDate: "2027-07-20 00:00:00",
      },
    ] as never);
    vi.mocked(getHsaLicensedPharmacies).mockResolvedValue([] as never);

    const result = await runQuery({
      query: "Healthcare supplier diligence for company ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "healthcare_supplier_diligence",
      toolsUsed: ["sg_business_dossier"],
    });
    expect(vi.mocked(getHsaHealthProductLicensees)).toHaveBeenCalledWith(
      expect.objectContaining({ companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", limit: 10 }),
    );
  });

  it("extracts a clean entity name from the healthcare supplier diligence prompt shape", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
        uen: "201012345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getHsaHealthProductLicensees).mockResolvedValue([
      {
        companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
        licenseType: "Controlled Drugs - Wholesale Licence",
        activityType: null,
        dosageForm: null,
        expiryDate: "2027-07-20 00:00:00",
      },
    ] as never);
    vi.mocked(getHsaLicensedPharmacies).mockResolvedValue([] as never);
    vi.mocked(getGeBIZTenders).mockResolvedValue([] as never);

    const result = await runQuery({
      query: "Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "healthcare_supplier_diligence",
    });
    expect(vi.mocked(getHsaHealthProductLicensees)).toHaveBeenCalledWith(
      expect.objectContaining({ companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", limit: 10 }),
    );
  });

  it("executes the hotel-operator lookup workflow with HLB scope", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([] as never);
    vi.mocked(getHlbHotels).mockResolvedValue([
      {
        name: "RAFFLES HOTEL SINGAPORE",
        category: "hospitality",
        subcategory: "hotel",
        address: "1 BEACH ROAD",
        postalCode: "189673",
        lat: 1.2948,
        lng: 103.8546,
        sourceAgency: "Hotels Licensing Board",
        sourceDataset: "Hotels",
        sourceUrl: "https://data.gov.sg/collections/140/view",
        lastUpdatedAt: "2024-04-17T18:17:50+08:00",
        keeperName: "RAFFLES HOTEL SINGAPORE",
        totalRooms: 115,
        url: null,
        incCrc: "Y",
      },
    ] as never);

    const result = await runQuery({
      query: "Hotel operator lookup for company Raffles Hotel Singapore",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "hotel_operator_lookup",
      toolsUsed: ["sg_business_dossier"],
    });
    expect(vi.mocked(getHlbHotels)).toHaveBeenCalledWith(
      expect.objectContaining({ keeperName: "Raffles Hotel Singapore", limit: 5 }),
    );
  });

  it("extracts a clean entity name from the hotel operator lookup prompt shape", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([] as never);
    vi.mocked(getHlbHotels)
      .mockResolvedValueOnce([] as never)
      .mockResolvedValueOnce([
        {
          name: "Marina Bay Sands",
          category: "hospitality",
          subcategory: "hotel",
          address: "10 BAYFRONT AVENUE",
          postalCode: "018956",
          lat: 1.2834,
          lng: 103.8607,
          sourceAgency: "Hotels Licensing Board",
          sourceDataset: "Hotels",
          sourceUrl: "https://data.gov.sg/collections/140/view",
          lastUpdatedAt: "2024-04-17T18:17:50+08:00",
          keeperName: "MARINA BAY SANDS PTE. LTD.",
          totalRooms: 2561,
          url: "https://www.marinabaysands.com",
          incCrc: "Y",
        },
      ] as never);

    const result = await runQuery({
      query: "Hotel operator lookup for Marina Bay Sands",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "hotel_operator_lookup",
    });
    expect(vi.mocked(getHlbHotels)).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ keeperName: "Marina Bay Sands", limit: 5 }),
    );
    expect(vi.mocked(getHlbHotels)).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ name: "Marina Bay Sands", limit: 5 }),
    );
  });

  it("extracts a clean entity name from the sector-scoped business diligence prompt shape", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([
      {
        companyName: "ABC CONSTRUCTION PTE LTD",
        classCode: "GB1",
        expiryDate: "2026-12-31",
      },
    ] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([
      {
        companyName: "ABC CONSTRUCTION PTE LTD",
        workhead: "CW01",
        grade: "C3",
        expiryDate: "2026-12-31",
      },
    ] as never);
    vi.mocked(getGeBIZTenders).mockResolvedValue([
      {
        agency: "MINDEF",
        tenderNo: "MINDEF000ETQ25000001",
        description: "Term contract for construction works",
        awardDate: "2025-01-15",
        status: "Awarded",
        supplierName: "ABC CONSTRUCTION PTE LTD",
        awardedAmount: 1250000,
        category: "Construction Works",
      },
    ] as never);

    const result = await runQuery({
      query: "Sector-scoped business diligence for company ABC CONSTRUCTION PTE LTD in construction procurement",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "sector_scoped_business_diligence",
    });
    expect(vi.mocked(getAcraEntities)).toHaveBeenCalledWith(
      expect.objectContaining({ entityName: "ABC CONSTRUCTION PTE LTD", limit: 5 }),
    );
    expect(vi.mocked(getBcaLicensedBuilders)).toHaveBeenCalledWith(
      expect.objectContaining({ companyName: "ABC CONSTRUCTION PTE LTD", limit: 5 }),
    );
    expect(vi.mocked(getGeBIZTenders)).toHaveBeenCalledWith(
      expect.objectContaining({ supplierName: "ABC CONSTRUCTION PTE LTD", limit: 10 }),
    );
  });
});
