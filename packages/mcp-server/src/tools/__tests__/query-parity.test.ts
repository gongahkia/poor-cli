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
  getDatasetResources: vi.fn(),
  getDatasetRows: vi.fn(),
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

vi.mock("../../apis/hdb/client.js", () => ({
  getHdbResalePrices: vi.fn(),
  getHdbRentalPrices: vi.fn(),
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

import { searchDatasets as singstatSearch } from "../../apis/singstat/client.js";
import { getTableData, getTimeSeries } from "../../apis/singstat/client.js";
import { query as masQuery } from "../../apis/mas/client.js";
import {
  convertSVY21toWGS84,
  geocode,
  getPopulationData,
  getRoute,
  reverseGeocode,
} from "../../apis/onemap/client.js";
import { getPropertyTransactions, uraFetch } from "../../apis/ura/client.js";
import {
  listCollections,
  getDatasetResources,
  getDatasetRows,
  searchDatasets as datagovSearch,
} from "../../apis/datagov/client.js";
import { getBusArrivals, getTrafficIncidents, getTrainAlerts } from "../../apis/lta/client.js";
import { getAirQuality, getForecast2Hr, getRainfall } from "../../apis/nea/client.js";
import { getHdbRentalPrices, getHdbResalePrices } from "../../apis/hdb/client.js";
import { getCeaSalespersons } from "../../apis/cea/client.js";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../../apis/bca/client.js";
import { getAcraEntities } from "../../apis/acra/client.js";
import { getPaCommunityOutlets } from "../../apis/pa/client.js";
import { getSportSgFacilities } from "../../apis/sportsg/client.js";
import { getEcdaChildcareCentres } from "../../apis/ecda/client.js";
import {
  getMsfFamilyServices,
  getMsfSocialServiceOffices,
  getMsfStudentCareServices,
} from "../../apis/msf/client.js";
import {
  handleSingStatBrowse,
  handleSingStatSearch,
  handleSingStatTable,
  handleSingStatTimeseries,
} from "../singstat-tools.js";
import { handleMasExchangeRates, handleMasInterestRates } from "../mas-tools.js";
import {
  handleOneMapConvertCoords,
  handleOneMapGeocode,
  handleOneMapPopulation,
  handleOneMapReverseGeocode,
  handleOneMapRoute,
} from "../onemap-tools.js";
import { handleUraDevCharges, handleUraPlanningArea } from "../ura-tools.js";
import {
  handleDatagovBrowse,
  handleDatagovResources,
  handleDatagovRows,
  handleDatagovSearch,
} from "../datagov-tools.js";
import {
  handleBusinessDossier,
  handleEnvironmentBrief,
  handleMacroBrief,
  handlePropertyBrief,
  handleTransportBrief,
} from "../brief-tools.js";
import { handleLtaBusArrivals } from "../lta-tools.js";
import { handleNeaForecast2Hr } from "../nea-tools.js";
import { handleHdbRentalPrices, handleHdbResalePrices } from "../hdb-tools.js";
import { handleCeaSalespersons } from "../cea-tools.js";
import {
  handleBcaLicensedBuilders,
  handleBcaRegisteredContractors,
} from "../bca-tools.js";
import { handleAcraEntities } from "../acra-tools.js";
import { handlePaCommunityOutlets } from "../pa-tools.js";
import { handleSportSgFacilities } from "../sportsg-tools.js";
import { handleEcdaChildcareCentres } from "../ecda-tools.js";
import {
  handleMsfFamilyServices,
  handleMsfSocialServiceOffices,
  handleMsfStudentCareServices,
} from "../msf-tools.js";
import { executeQueryStep } from "../query-tool.js";

const normalizeBriefResult = (result: Awaited<ReturnType<typeof executeQueryStep>>) => {
  const normalized = structuredClone(result);
  const record = normalized.structuredContent?.["record"];
  let content = normalized.content;

  if (
    typeof record === "object"
    && record !== null
    && "freshness" in record
    && Array.isArray(record["freshness"])
  ) {
    for (const item of record["freshness"]) {
      if (typeof item === "object" && item !== null && "observedAt" in item) {
        item["observedAt"] = "__normalized__";
      }
    }
  }

  const firstContent = normalized.content[0];
  if (firstContent?.type === "text") {
    try {
      const parsed = JSON.parse(firstContent.text) as Record<string, unknown>;
      const freshness = parsed["freshness"];
      if (Array.isArray(freshness)) {
        for (const item of freshness) {
          if (typeof item === "object" && item !== null && "observedAt" in item) {
            item["observedAt"] = "__normalized__";
          }
        }
        content = [{
          ...firstContent,
          text: JSON.stringify(parsed, null, 2),
        }];
      }
    } catch {
      // Non-JSON tool outputs are compared as-is.
    }
  }

  return {
    ...normalized,
    content,
  };
};

describe("sg_query parity", () => {
  beforeEach(() => {
    vi.mocked(singstatSearch).mockReset();
    vi.mocked(getTableData).mockReset();
    vi.mocked(getTimeSeries).mockReset();
    vi.mocked(masQuery).mockReset();
    vi.mocked(geocode).mockReset();
    vi.mocked(reverseGeocode).mockReset();
    vi.mocked(getRoute).mockReset();
    vi.mocked(convertSVY21toWGS84).mockReset();
    vi.mocked(getPopulationData).mockReset();
    vi.mocked(getPropertyTransactions).mockReset();
    vi.mocked(uraFetch).mockReset();
    vi.mocked(datagovSearch).mockReset();
    vi.mocked(listCollections).mockReset();
    vi.mocked(getDatasetResources).mockReset();
    vi.mocked(getDatasetRows).mockReset();
    vi.mocked(getBusArrivals).mockReset();
    vi.mocked(getTrainAlerts).mockReset();
    vi.mocked(getTrafficIncidents).mockReset();
    vi.mocked(getForecast2Hr).mockReset();
    vi.mocked(getAirQuality).mockReset();
    vi.mocked(getRainfall).mockReset();
    vi.mocked(getHdbResalePrices).mockReset();
    vi.mocked(getHdbRentalPrices).mockReset();
    vi.mocked(getCeaSalespersons).mockReset();
    vi.mocked(getBcaLicensedBuilders).mockReset();
    vi.mocked(getBcaRegisteredContractors).mockReset();
    vi.mocked(getAcraEntities).mockReset();
    vi.mocked(getPaCommunityOutlets).mockReset();
    vi.mocked(getSportSgFacilities).mockReset();
    vi.mocked(getEcdaChildcareCentres).mockReset();
    vi.mocked(getMsfFamilyServices).mockReset();
    vi.mocked(getMsfStudentCareServices).mockReset();
    vi.mocked(getMsfSocialServiceOffices).mockReset();
  });

  it("matches the direct SingStat search handler", async () => {
    vi.mocked(singstatSearch).mockResolvedValue([
      { id: "M015631", title: "GDP", theme: "Economy", subject: "National Accounts", topic: "GDP", frequency: "Annual" },
    ]);

    const input = { keyword: "GDP Singapore" };

    await expect(executeQueryStep("sg_singstat_search", input)).resolves.toEqual(
      await handleSingStatSearch(input),
    );
  });

  it("matches the direct SingStat table handler", async () => {
    vi.mocked(getTableData).mockResolvedValue({
      metadata: {
        title: "Singapore GDP",
        tableId: "M015631",
        frequency: "Annual",
        footnote: "",
        source: "SingStat",
        lastUpdated: "2026-03-01",
      },
      rows: [
        { year: "2024", value: 712345.6 },
      ],
    } as never);

    const input = { tableId: "M015631", format: "json" } as const;

    await expect(executeQueryStep("sg_singstat_table", input)).resolves.toEqual(
      await handleSingStatTable(input),
    );
  });

  it("matches the direct SingStat timeseries handler", async () => {
    vi.mocked(getTimeSeries).mockResolvedValue([
      { period: "2022", value: 3.2 },
      { period: "2023", value: 3.4 },
    ] as never);

    const input = {
      tableId: "M015631",
      indicator: "GDP at current market prices",
      startYear: 2022,
      endYear: 2023,
      format: "json",
    } as const;

    await expect(executeQueryStep("sg_singstat_timeseries", input)).resolves.toEqual(
      await handleSingStatTimeseries(input),
    );
  });

  it("matches the direct SingStat browse handler", async () => {
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

    const input = { category: "Transport" } as const;

    await expect(executeQueryStep("sg_singstat_browse", input)).resolves.toEqual(
      await handleSingStatBrowse(input),
    );
  });

  it("matches the direct MAS exchange-rate handler", async () => {
    vi.mocked(masQuery).mockResolvedValue([
      { _id: 1, end_of_day: "2024-01-31", preliminary: "N", usd_sgd: "1.35" },
    ]);

    const input = { currency: "USD", date: "2024-01-31", format: "json" } as const;

    await expect(executeQueryStep("sg_mas_exchange_rates", input)).resolves.toEqual(
      await handleMasExchangeRates(input),
    );
  });

  it("matches the direct MAS interest-rate handler", async () => {
    vi.mocked(masQuery).mockResolvedValue([
      { _id: 1, end_of_day: "2024-01-31", preliminary: "N", sora: "3.56" },
    ]);

    const input = { date: "2024-01-31", format: "json" } as const;

    await expect(executeQueryStep("sg_mas_interest_rates", input)).resolves.toEqual(
      await handleMasInterestRates(input),
    );
  });

  it("matches the direct OneMap geocode handler", async () => {
    vi.mocked(geocode).mockResolvedValue([
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

    const input = { searchVal: "048616" };

    await expect(executeQueryStep("sg_onemap_geocode", input)).resolves.toEqual(
      await handleOneMapGeocode(input),
    );
  });

  it("matches the direct OneMap reverse-geocode handler", async () => {
    vi.mocked(reverseGeocode).mockResolvedValue({
      block: "1",
      road: "RAFFLES PLACE",
      building: "ONE RAFFLES PLACE",
      postal: "048616",
      x: 28001,
      y: 38744,
      lat: 1.284,
      lng: 103.851,
    } as never);

    const input = { lat: 1.284, lng: 103.851 } as const;

    await expect(executeQueryStep("sg_onemap_reverse_geocode", input)).resolves.toEqual(
      await handleOneMapReverseGeocode(input),
    );
  });

  it("matches the direct OneMap route handler", async () => {
    vi.mocked(getRoute).mockResolvedValue({
      totalDistance: 1500,
      totalTime: 900,
      instructions: [
        {
          instruction: "Walk straight",
          road: "North Bridge Road",
          distance: 250,
          lat: 1.29,
          lng: 103.85,
        },
      ],
      routeGeometry: [],
    } as never);

    const input = {
      startLat: 1.2894,
      startLng: 103.8491,
      endLat: 1.284,
      endLng: 103.851,
      routeType: "walk",
    } as const;

    await expect(executeQueryStep("sg_onemap_route", input)).resolves.toEqual(
      await handleOneMapRoute(input),
    );
  });

  it("matches the direct OneMap coordinate-conversion handler", async () => {
    vi.mocked(convertSVY21toWGS84).mockResolvedValue({
      lat: 1.284,
      lng: 103.851,
    } as never);

    const input = { from: "SVY21", x: 28001, y: 38744 } as const;

    await expect(executeQueryStep("sg_onemap_convert_coords", input)).resolves.toEqual(
      await handleOneMapConvertCoords(input),
    );
  });

  it("matches the direct OneMap population handler", async () => {
    vi.mocked(getPopulationData).mockResolvedValue({
      planningArea: "Tampines",
      year: "2020",
      data: [{ age_group: "0-4", total: "1200" }],
    });

    const input = {
      planningArea: "Tampines",
      dataType: "getPopulationAgeGroup",
      format: "json",
    } as const;

    await expect(executeQueryStep("sg_onemap_population", input)).resolves.toEqual(
      await handleOneMapPopulation(input),
    );
  });

  it("matches the direct URA planning-area handler", async () => {
    vi.mocked(geocode).mockResolvedValue([
      {
        address: "Bedok",
        building: "TEST",
        postal: "460000",
        lat: 1.324,
        lng: 103.93,
        x: 0,
        y: 0,
      },
    ]);
    vi.mocked(uraFetch).mockResolvedValue({
      Status: "OK",
      Result: [{ pln_area_n: "BEDOK", region: "East Region" }],
    });

    const input = { planningArea: "Bedok" };

    await expect(executeQueryStep("sg_ura_planning_area", input)).resolves.toEqual(
      await handleUraPlanningArea(input),
    );
  });

  it("matches the direct URA development-charge handler", async () => {
    vi.mocked(uraFetch).mockResolvedValue({
      Status: "OK",
      Result: [
        { use_grp: "Residential", sector: "A", rate: "3200", effDate: "2026-03-01" },
      ],
    } as never);

    const input = { useGroup: "Residential", sector: "A" } as const;

    await expect(executeQueryStep("sg_ura_dev_charges", input)).resolves.toEqual(
      await handleUraDevCharges(input),
    );
  });

  it("matches the direct data.gov search handler", async () => {
    vi.mocked(datagovSearch).mockResolvedValue([
      {
        datasetId: "hawker-centres",
        name: "Hawker Centres",
        description: "Locations of hawker centres",
        managedByAgencyName: "NEA",
        format: "CSV",
        lastUpdatedAt: "2024-01-31",
        createdAt: "2020-01-01",
        status: "active",
      },
    ]);

    const input = { keyword: "hawker centres" };

    await expect(executeQueryStep("sg_datagov_search", input)).resolves.toEqual(
      await handleDatagovSearch(input),
    );
  });

  it("matches the direct data.gov resource-inspection handler", async () => {
    vi.mocked(getDatasetResources).mockResolvedValue({
      datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      name: "HDB Resale Flat Prices",
      description: "Resale flat prices",
      status: "active",
      format: "CSV",
      createdAt: "2020-01-01",
      lastUpdatedAt: "2026-03-01",
      managedByAgencyName: "HDB",
      collectionIds: ["housing"],
      contactEmails: ["data@hdb.gov.sg"],
      datasetSize: 2048,
      resources: [{
        resourceId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        name: "HDB Resale Flat Prices",
        format: "CSV",
        machineReadable: true,
        columns: [
          {
            key: "month",
            name: "month",
            title: "Month",
            dataType: "text",
            index: 1,
            isCategorical: false,
          },
        ],
      }],
    });

    const input = { datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc", format: "json" } as const;

    await expect(executeQueryStep("sg_datagov_resources", input)).resolves.toEqual(
      await handleDatagovResources(input),
    );
  });

  it("matches the direct data.gov bounded-row handler", async () => {
    vi.mocked(getDatasetRows).mockResolvedValue({
      datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      datasetName: "HDB Resale Flat Prices",
      resourceId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      total: 1,
      offset: 0,
      limit: 1,
      fields: [{ id: "town", type: "text" }],
      records: [{ town: "BEDOK" }],
    });

    const input = { datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc", limit: 1, format: "json" } as const;

    await expect(executeQueryStep("sg_datagov_rows", input)).resolves.toEqual(
      await handleDatagovRows(input),
    );
  });

  it("matches the direct data.gov browse handler", async () => {
    vi.mocked(listCollections).mockResolvedValue([
      { collectionId: "housing", name: "Housing", datasetCount: 12 },
    ] as never);

    const input = {} as const;

    await expect(executeQueryStep("sg_datagov_browse", input)).resolves.toEqual(
      await handleDatagovBrowse(input),
    );
  });

  it("matches the direct transport brief handler", async () => {
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [{ line: "NSL" }],
      messages: [{ content: "Minor delay", createdDate: "2026-03-26T08:00:00+08:00" }],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([
      { type: "Road Works" },
    ] as never);

    const input = { format: "json" } as const;

    const [queryResult, directResult] = await Promise.all([
      executeQueryStep("sg_transport_brief", input),
      handleTransportBrief(input),
    ]);

    expect(normalizeBriefResult(queryResult)).toEqual(normalizeBriefResult(directResult));
  });

  it("matches the direct environment brief handler", async () => {
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

    const input = { area: "Tampines", region: "East", stationId: "S107", format: "json" } as const;

    const [queryResult, directResult] = await Promise.all([
      executeQueryStep("sg_environment_brief", input),
      handleEnvironmentBrief(input),
    ]);

    expect(normalizeBriefResult(queryResult)).toEqual(normalizeBriefResult(directResult));
  });

  it("matches the direct LTA bus-arrivals handler", async () => {
    vi.mocked(getBusArrivals).mockResolvedValue([
      {
        busStopCode: "83139",
        serviceNo: "851",
        operator: "SBST",
        arrivals: [
          {
            ordinal: 1,
            estimatedArrival: "2026-03-23T08:05:00+08:00",
            load: "SEA",
            feature: "WAB",
            type: "SD",
            monitored: true,
            visitNumber: "1",
            originCode: "59009",
            destinationCode: "58009",
            lat: 1.3345,
            lng: 103.8974,
          },
        ],
      },
    ]);

    const input = { busStopCode: "83139", serviceNo: "851", format: "json" } as const;

    await expect(executeQueryStep("sg_lta_bus_arrivals", input)).resolves.toEqual(
      await handleLtaBusArrivals(input),
    );
  });

  it("matches the direct NEA forecast handler", async () => {
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Tampines",
        forecast: "Partly Cloudy",
        validFrom: "2026-03-23T08:00:00+08:00",
        validTo: "2026-03-23T10:00:00+08:00",
        validText: "8 AM to 10 AM",
        updatedAt: "2026-03-23T08:00:00+08:00",
        lat: 1.3526,
        lng: 103.945,
      },
    ]);

    const input = { area: "Tampines", format: "json" } as const;

    await expect(executeQueryStep("sg_nea_forecast_2hr", input)).resolves.toEqual(
      await handleNeaForecast2Hr(input),
    );
  });

  it("matches the direct HDB resale handler", async () => {
    vi.mocked(getHdbResalePrices).mockResolvedValue([
      {
        month: "2026-02",
        town: "BEDOK",
        flatType: "4 ROOM",
        block: "101",
        streetName: "BEDOK NORTH AVE 4",
        storeyRange: "10 TO 12",
        floorAreaSqm: 92,
        flatModel: "Model A",
        leaseCommenceDate: 1998,
        remainingLease: "71 years 2 months",
        resalePrice: 560000,
      },
    ]);

    const input = { town: "Bedok", startMonth: "2026-01", endMonth: "2026-03", format: "json" } as const;

    await expect(executeQueryStep("sg_hdb_resale_prices", input)).resolves.toEqual(
      await handleHdbResalePrices(input),
    );
  });

  it("matches the direct HDB rental handler", async () => {
    vi.mocked(getHdbRentalPrices).mockResolvedValue([
      {
        month: "2026-02",
        town: "BEDOK",
        flatType: "4 ROOM",
        block: "101",
        streetName: "BEDOK NORTH AVE 4",
        rents: 2600,
      },
    ] as never);

    const input = { town: "Bedok", flatType: "4 ROOM", format: "json" } as const;

    await expect(executeQueryStep("sg_hdb_rental_prices", input)).resolves.toEqual(
      await handleHdbRentalPrices(input),
    );
  });

  it("matches the direct CEA salesperson handler", async () => {
    vi.mocked(getCeaSalespersons).mockResolvedValue([
      {
        salespersonName: "JANE TAN",
        registrationNo: "R123456A",
        registrationStartDate: "2011-01-01",
        registrationEndDate: "2026-12-31",
        estateAgentName: "ERA REALTY NETWORK PTE LTD",
        estateAgentLicenseNo: "L3002382K",
      },
    ]);

    const input = { registrationNo: "R123456A", format: "json" } as const;

    await expect(executeQueryStep("sg_cea_salespersons", input)).resolves.toEqual(
      await handleCeaSalespersons(input),
    );
  });

  it("matches the direct BCA licensed-builder handler", async () => {
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

    const input = { companyName: "ABC CONSTRUCTION PTE LTD", format: "json" } as const;

    await expect(executeQueryStep("sg_bca_licensed_builders", input)).resolves.toEqual(
      await handleBcaLicensedBuilders(input),
    );
  });

  it("matches the direct BCA registered-contractor handler", async () => {
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

    const input = { workhead: "CW01", companyName: "ABC CONSTRUCTION PTE LTD", format: "json" } as const;

    await expect(executeQueryStep("sg_bca_registered_contractors", input)).resolves.toEqual(
      await handleBcaRegisteredContractors(input),
    );
  });

  it("matches the direct ACRA entity handler", async () => {
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

    const input = { entityName: "ABC CONSTRUCTION PTE LTD", format: "json" } as const;

    await expect(executeQueryStep("sg_acra_entities", input)).resolves.toEqual(
      await handleAcraEntities(input),
    );
  });

  it("matches the direct business dossier handler", async () => {
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
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([]);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([]);
    vi.mocked(getCeaSalespersons).mockResolvedValue([]);

    const input = { entityName: "ABC CONSTRUCTION PTE LTD", format: "json" } as const;

    const [queryResult, directResult] = await Promise.all([
      executeQueryStep("sg_business_dossier", input),
      handleBusinessDossier(input),
    ]);

    expect(normalizeBriefResult(queryResult)).toEqual(normalizeBriefResult(directResult));
  });

  it("matches the direct property brief handler", async () => {
    vi.mocked(geocode).mockResolvedValue([
      {
        address: "BEDOK",
        building: "TEST",
        postal: "460000",
        lat: 1.324,
        lng: 103.93,
        x: 0,
        y: 0,
      },
    ]);
    vi.mocked(uraFetch).mockResolvedValue({
      Status: "OK",
      Result: [{ pln_area_n: "BEDOK", region: "East Region" }],
    });
    vi.mocked(getPropertyTransactions).mockResolvedValue([
      {
        project: "BEDOK RESIDENCES",
        street: "BEDOK NORTH AVE 4",
        x: "0",
        y: "0",
        marketSegment: "RCR",
        area: "90",
        floorRange: "10 TO 12",
        noOfUnits: "1",
        contractDate: "2026-03",
        typeOfSale: "Resale",
        price: "1200000",
        propertyType: "residential",
        district: "16",
        typeOfArea: "sqm",
        tenure: "99 years",
        nettPrice: "1200000",
      },
    ]);
    vi.mocked(getHdbResalePrices).mockResolvedValue([
      {
        month: "2026-02",
        town: "BEDOK",
        flatType: "4 ROOM",
        block: "101",
        streetName: "BEDOK NORTH AVE 4",
        storeyRange: "10 TO 12",
        floorAreaSqm: 92,
        flatModel: "Model A",
        leaseCommenceDate: 1998,
        remainingLease: "71 years 2 months",
        resalePrice: 560000,
      },
    ]);
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Bedok",
        forecast: "Partly Cloudy",
        validFrom: "2026-03-23T08:00:00+08:00",
        validTo: "2026-03-23T10:00:00+08:00",
        validText: "8 AM to 10 AM",
        updatedAt: "2026-03-23T08:00:00+08:00",
        lat: 1.3526,
        lng: 103.945,
      },
    ]);
    vi.mocked(getAirQuality).mockResolvedValue([
      {
        region: "East",
        psi24h: 42,
        pm25OneHourly: 12,
        pm25TwentyFourHourly: 18,
        updatedAt: "2026-03-23T08:00:00+08:00",
        lat: 1.35,
        lng: 103.94,
      },
    ]);

    const input = { planningArea: "Bedok", flatType: "4 ROOM", format: "json" } as const;

    const [queryResult, directResult] = await Promise.all([
      executeQueryStep("sg_property_brief", input),
      handlePropertyBrief(input),
    ]);

    expect(normalizeBriefResult(queryResult)).toEqual(normalizeBriefResult(directResult));
  });

  it("matches the direct macro brief handler", async () => {
    vi.mocked(masQuery).mockImplementation(async (resourceId) => {
      if (resourceId === "95932927-c8bc-4e7a-b484-68a66a24edfe") {
        return [
          { _id: 1, end_of_day: "2024-01-31", preliminary: "0", usd_sgd: "1.35" },
          { _id: 2, end_of_day: "2024-01-30", preliminary: "0", usd_sgd: "1.34" },
        ];
      }
      if (resourceId === "9a0bf149-308c-4bd2-832d-76c8e6cb47ed") {
        return [
          { _id: 1, end_of_day: "2024-01-31", preliminary: "0", sora_3m: "3.56" },
          { _id: 2, end_of_day: "2024-01-30", preliminary: "0", sora_3m: "3.51" },
        ];
      }
      return [
        { _id: 1, end_of_day: "2024-01-31", preliminary: "0", total_deposits: "100" },
        { _id: 2, end_of_day: "2024-01-30", preliminary: "0", total_deposits: "99" },
      ];
    });
    vi.mocked(singstatSearch).mockImplementation(async (keyword) => {
      if (keyword === "Singapore GDP") {
        return [
          { id: "M015631", title: "Singapore GDP", theme: "Economy", subject: "National Accounts", topic: "GDP", frequency: "Annual" },
        ];
      }
      if (keyword === "Singapore CPI inflation") {
        return [
          { id: "M015631", title: "Singapore GDP", theme: "Economy", subject: "National Accounts", topic: "GDP", frequency: "Annual" },
          { id: "M212261", title: "Singapore CPI", theme: "Economy", subject: "Prices", topic: "CPI", frequency: "Monthly" },
        ];
      }
      return [];
    });

    const input = { currency: "USD", format: "json" } as const;

    const [queryResult, directResult] = await Promise.all([
      executeQueryStep("sg_macro_brief", input),
      handleMacroBrief(input),
    ]);

    expect(normalizeBriefResult(queryResult)).toEqual(normalizeBriefResult(directResult));
    const briefPayload = JSON.parse((directResult.content[0] as { text?: string }).text ?? "");
    const evidenceByLabel = new Map(briefPayload.evidence.map((item: { label: string; value: unknown }) => [item.label, item.value]));
    const summaryByLabel = new Map(briefPayload.summary.map((item: { label: string; value: unknown }) => [item.label, item.value]));
    expect(evidenceByLabel.get("Primary SORA key")).toBe("sora_3m");
    expect(evidenceByLabel.get("Primary banking key")).toBe("total_deposits");
    expect(summaryByLabel.get("CPI table ID")).toBe("M212261");
    expect(summaryByLabel.get("CPI table ID")).not.toBe(summaryByLabel.get("GDP table ID"));
  });

  it("matches the direct PA community outlets handler", async () => {
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

    const input = { type: "community_club", postalCode: "048616", format: "json" } as const;

    await expect(executeQueryStep("sg_pa_community_outlets", input)).resolves.toEqual(
      await handlePaCommunityOutlets(input),
    );
  });

  it("matches the direct SportSG facilities handler", async () => {
    vi.mocked(getSportSgFacilities).mockResolvedValue([
      {
        name: "Downtown Swimming Complex",
        category: "sports",
        subcategory: "swimming_complex",
        address: "5, Raffles Place",
        postalCode: "048618",
        lat: 1.2842,
        lng: 103.8513,
        sourceAgency: "Sport Singapore",
        sourceDataset: "SportSG Sport Facilities (GEOJSON)",
        sourceUrl: "https://data.gov.sg/datasets/d_9b87bab59d036a60fad2a91530e10773/view",
        lastUpdatedAt: "2024-04-17T18:17:50+08:00",
        facilityType: "swimming_complex",
        detailsUrl: "https://www.activesgcircle.gov.sg/facilities",
      },
    ] as never);

    const input = { facilityType: "swimming_complex", postalCode: "048618", format: "json" } as const;

    await expect(executeQueryStep("sg_sportsg_facilities", input)).resolves.toEqual(
      await handleSportSgFacilities(input),
    );
  });

  it("matches the direct ECDA childcare handler", async () => {
    vi.mocked(getEcdaChildcareCentres).mockResolvedValue([
      {
        name: "MY FIRST SKOOL @ ONE RAFFLES PLACE",
        category: "childcare",
        subcategory: "child care / infant care",
        address: "1 Raffles Place, #01-01",
        postalCode: "048616",
        lat: 1.284,
        lng: 103.851,
        sourceAgency: "Early Childhood Development Agency",
        sourceDataset: "Child Care Services + Listing of Centres",
        sourceUrl: "https://data.gov.sg/datasets/d_5d668e3f544335f8028f546827b773b4/view",
        lastUpdatedAt: "2026-03-20",
        centreCode: "CC0001",
        centreType: "CC",
        operatorType: "PAP Community Foundation",
        serviceModel: "CHILD CARE / INFANT CARE",
        contactNo: "61234567",
        email: "info@myfirstskool.sg",
        website: "https://www.myfirstskool.com",
        hasVacancy: true,
        infantVacancyCurrentMonth: "available",
        playgroupVacancyCurrentMonth: "limited",
        n1VacancyCurrentMonth: "full",
        n2VacancyCurrentMonth: "full",
        k1VacancyCurrentMonth: "available",
        k2VacancyCurrentMonth: "full",
      },
    ] as never);

    const input = { centreType: "CC", postalCode: "048616", hasVacancy: true, format: "json" } as const;

    await expect(executeQueryStep("sg_ecda_childcare_centres", input)).resolves.toEqual(
      await handleEcdaChildcareCentres(input),
    );
  });

  it("matches the direct MSF family services handler", async () => {
    vi.mocked(getMsfFamilyServices).mockResolvedValue([
      {
        name: "Allkin Family Service Centre @ Ang Mo Kio 230",
        category: "social_support",
        subcategory: "family_service_centre",
        address: "Blk 230 Ang Mo Kio Ave 3 #01-1264",
        postalCode: "560230",
        lat: 1.3688544443488972,
        lng: 103.83789640387423,
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

    const input = { postalCode: "560230", format: "json" } as const;

    await expect(executeQueryStep("sg_msf_family_services", input)).resolves.toEqual(
      await handleMsfFamilyServices(input),
    );
  });

  it("matches the direct MSF student care handler", async () => {
    vi.mocked(getMsfStudentCareServices).mockResolvedValue([
      {
        name: "YMCA Student Care Centre @ Canberra",
        category: "childcare",
        subcategory: "student_care",
        address: "471, Sembawang Drive, #1 421, Singapore 750471",
        postalCode: "750471",
        lat: 1.4520108099275582,
        lng: 103.81584893819745,
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

    const input = { postalCode: "750471", auditStatus: "Grade A", scfaOnly: true, format: "json" } as const;

    await expect(executeQueryStep("sg_msf_student_care_services", input)).resolves.toEqual(
      await handleMsfStudentCareServices(input),
    );
  });

  it("matches the direct MSF social service offices handler", async () => {
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

    const input = { postalCode: "140040", format: "json" } as const;

    await expect(executeQueryStep("sg_msf_social_service_offices", input)).resolves.toEqual(
      await handleMsfSocialServiceOffices(input),
    );
  });
});
