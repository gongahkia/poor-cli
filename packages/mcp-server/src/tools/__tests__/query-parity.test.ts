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

vi.mock("../../apis/hdb/client.js", () => ({
  getHdbResalePrices: vi.fn(),
  getHdbRentalPrices: vi.fn(),
}));

import { searchDatasets as singstatSearch } from "../../apis/singstat/client.js";
import { query as masQuery } from "../../apis/mas/client.js";
import { geocode, getPopulationData } from "../../apis/onemap/client.js";
import { uraFetch } from "../../apis/ura/client.js";
import { searchDatasets as datagovSearch } from "../../apis/datagov/client.js";
import { getBusArrivals } from "../../apis/lta/client.js";
import { getForecast2Hr } from "../../apis/nea/client.js";
import { getHdbResalePrices } from "../../apis/hdb/client.js";
import { handleSingStatSearch } from "../singstat-tools.js";
import { handleMasExchangeRates, handleMasInterestRates } from "../mas-tools.js";
import { handleOneMapGeocode, handleOneMapPopulation } from "../onemap-tools.js";
import { handleUraPlanningArea } from "../ura-tools.js";
import { handleDatagovSearch } from "../datagov-tools.js";
import { handleLtaBusArrivals } from "../lta-tools.js";
import { handleNeaForecast2Hr } from "../nea-tools.js";
import { handleHdbResalePrices } from "../hdb-tools.js";
import { executeQueryStep } from "../query-tool.js";

describe("sg_query parity", () => {
  beforeEach(() => {
    vi.mocked(singstatSearch).mockReset();
    vi.mocked(masQuery).mockReset();
    vi.mocked(geocode).mockReset();
    vi.mocked(getPopulationData).mockReset();
    vi.mocked(uraFetch).mockReset();
    vi.mocked(datagovSearch).mockReset();
    vi.mocked(getBusArrivals).mockReset();
    vi.mocked(getForecast2Hr).mockReset();
    vi.mocked(getHdbResalePrices).mockReset();
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
});
