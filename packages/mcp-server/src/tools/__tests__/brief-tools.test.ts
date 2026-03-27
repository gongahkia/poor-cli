import { beforeEach, describe, expect, it, vi } from "vitest";
import { BriefArtifactSchema, MasDataset } from "@sg-apis/shared";

vi.mock("../../apis/acra/client.js", () => ({
  getAcraEntities: vi.fn(),
}));

vi.mock("../../apis/bca/client.js", () => ({
  getBcaLicensedBuilders: vi.fn(),
  getBcaRegisteredContractors: vi.fn(),
}));

vi.mock("../../apis/cea/client.js", () => ({
  getCeaSalespersons: vi.fn(),
}));

vi.mock("../../apis/hdb/client.js", () => ({
  getHdbResalePrices: vi.fn(),
}));

vi.mock("../../apis/lta/client.js", () => ({
  getBusArrivals: vi.fn(),
  getTrainAlerts: vi.fn(),
  getTrafficIncidents: vi.fn(),
}));

vi.mock("../../apis/nea/client.js", () => ({
  getAirQuality: vi.fn(),
  getForecast2Hr: vi.fn(),
  getRainfall: vi.fn(),
}));

vi.mock("../../apis/onemap/client.js", () => ({
  geocode: vi.fn(),
}));

vi.mock("../../apis/singstat/client.js", () => ({
  searchDatasets: vi.fn(),
}));

vi.mock("../../apis/ura/client.js", () => ({
  getPropertyTransactions: vi.fn(),
}));

vi.mock("../mas-tools.js", () => ({
  fetchNormalizedMasRecords: vi.fn(),
}));

vi.mock("../ura-tools.js", () => ({
  lookupPlanningArea: vi.fn(),
}));

import { getAcraEntities } from "../../apis/acra/client.js";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../../apis/bca/client.js";
import { getHdbResalePrices } from "../../apis/hdb/client.js";
import {
  getBusArrivals,
  getTrainAlerts,
  getTrafficIncidents,
} from "../../apis/lta/client.js";
import {
  getAirQuality,
  getForecast2Hr,
  getRainfall,
} from "../../apis/nea/client.js";
import { searchDatasets as searchSingStatDatasets } from "../../apis/singstat/client.js";
import { getPropertyTransactions } from "../../apis/ura/client.js";
import { fetchNormalizedMasRecords } from "../mas-tools.js";
import { lookupPlanningArea } from "../ura-tools.js";
import {
  handleBusinessDossier,
  handleEnvironmentBrief,
  handleMacroBrief,
  handlePropertyBrief,
  handleTransportBrief,
} from "../brief-tools.js";

const parseBrief = (resultText: string) => {
  return BriefArtifactSchema.parse(JSON.parse(resultText));
};

const expectMarkdownSections = (text: string) => {
  expect(text).toContain("### Sources");
  expect(text).toContain("### Freshness");
  expect(text).toContain("### What This Does Not Do");
};

describe("brief tools", () => {
  beforeEach(() => {
    vi.mocked(getAcraEntities).mockReset();
    vi.mocked(getBcaLicensedBuilders).mockReset();
    vi.mocked(getBcaRegisteredContractors).mockReset();
    vi.mocked(getHdbResalePrices).mockReset();
    vi.mocked(getBusArrivals).mockReset();
    vi.mocked(getTrainAlerts).mockReset();
    vi.mocked(getTrafficIncidents).mockReset();
    vi.mocked(getAirQuality).mockReset();
    vi.mocked(getForecast2Hr).mockReset();
    vi.mocked(getRainfall).mockReset();
    vi.mocked(searchSingStatDatasets).mockReset();
    vi.mocked(getPropertyTransactions).mockReset();
    vi.mocked(fetchNormalizedMasRecords).mockReset();
    vi.mocked(lookupPlanningArea).mockReset();
  });

  it("returns the expanded business dossier envelope", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
        noOfOfficers: 3,
        annualReturnDate: "2026-03-01",
      },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([
      {
        classCode: "GB1",
        expiryDate: "2026-12-31",
      },
    ] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([
      {
        workhead: "CW01",
        expiryDate: "2026-12-31",
      },
    ] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "ABC CONSTRUCTION PTE LTD",
      format: "json",
    });
    const jsonText = jsonResult.content[0]?.text ?? "";
    const payload = parseBrief(jsonText);

    expect(payload.title).toBe("Business Dossier");
    expect(payload.provenance).toHaveLength(4);
    expect(payload.freshness).toHaveLength(4);
    expect(payload.limits.length).toBeGreaterThan(0);

    const markdownResult = await handleBusinessDossier({
      entityName: "ABC CONSTRUCTION PTE LTD",
      format: "markdown",
    });
    expectMarkdownSections(markdownResult.content[0]?.text ?? "");
  });

  it("returns the expanded property brief envelope", async () => {
    vi.mocked(lookupPlanningArea).mockResolvedValue([
      { planningArea: "Bedok", region: "East Region" },
    ] as never);
    vi.mocked(getPropertyTransactions).mockResolvedValue([
      { price: "1200000", contractDate: "2026-03" },
    ] as never);
    vi.mocked(getHdbResalePrices).mockResolvedValue([
      { resalePrice: 560000, month: "2026-03" },
    ] as never);
    vi.mocked(getForecast2Hr).mockResolvedValue([
      { area: "Bedok", forecast: "Cloudy", updatedAt: "2026-03-26T08:00:00+08:00" },
    ] as never);
    vi.mocked(getAirQuality).mockResolvedValue([
      { region: "East", psi24h: 42, updatedAt: "2026-03-26T08:00:00+08:00" },
    ] as never);
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [{ line: "EWL" }],
      messages: [{ content: "Delay", createdDate: "2026-03-26T08:00:00+08:00" }],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([
      { type: "Accident" },
    ] as never);

    const jsonResult = await handlePropertyBrief({
      planningArea: "Bedok",
      includeTransport: true,
      includeEnvironment: true,
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");

    expect(payload.title).toBe("Property Brief");
    expect(payload.provenance.length).toBeGreaterThanOrEqual(6);
    expect(payload.records["trainAlerts"]).toBeDefined();

    const markdownResult = await handlePropertyBrief({
      planningArea: "Bedok",
      includeTransport: true,
      includeEnvironment: true,
      format: "markdown",
    });
    expectMarkdownSections(markdownResult.content[0]?.text ?? "");
  });

  it("returns the expanded macro brief envelope", async () => {
    vi.mocked(fetchNormalizedMasRecords).mockImplementation(async (dataset) => {
      if (dataset === MasDataset.EXCHANGE_RATES) {
        return [
          { date: "2026-03-26", usd_sgd: 1.35 },
          { date: "2026-03-25", usd_sgd: 1.34 },
        ] as never;
      }
      if (dataset === MasDataset.INTEREST_RATES_SORA) {
        return [
          { date: "2026-03-26", preliminary: 0, sora_3m: 3.2 },
          { date: "2026-03-25", preliminary: 0, sora_3m: 3.1 },
        ] as never;
      }
      return [
        { date: "2026-03-26", preliminary: 0, total_deposits: 1000 },
        { date: "2026-03-25", preliminary: 0, total_deposits: 980 },
      ] as never;
    });
    vi.mocked(searchSingStatDatasets)
      .mockResolvedValueOnce([{ id: "gdp", title: "Singapore GDP" }] as never)
      .mockResolvedValueOnce([
        { id: "gdp-wrong", title: "Gross Domestic Product, Year On Year Growth Rate, Quarterly", topic: "Gross Domestic Product (GDP)" },
        { id: "cpi", title: "Consumer Price Index, All Items, Monthly", topic: "Consumer Price Index (CPI)" },
      ] as never);

    const jsonResult = await handleMacroBrief({
      currency: "USD",
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");
    const summaryByLabel = new Map(payload.summary.map((item) => [item.label, item.value]));
    const evidenceByLabel = new Map(payload.evidence.map((item) => [item.label, item.value]));

    expect(payload.title).toBe("Macro Brief");
    expect(payload.provenance).toHaveLength(4);
    expect(payload.summary.some((item) => item.label === "GDP table ID")).toBe(true);
    expect(summaryByLabel.get("3M SORA")).toBe(3.2);
    expect(summaryByLabel.get("Total deposits")).toBe(1000);
    expect(summaryByLabel.get("CPI table ID")).toBe("cpi");
    expect(summaryByLabel.get("CPI table ID")).not.toBe(summaryByLabel.get("GDP table ID"));
    expect(evidenceByLabel.get("Primary SORA key")).toBe("sora_3m");
    expect(evidenceByLabel.get("Primary banking key")).toBe("total_deposits");
    expect(evidenceByLabel.get("Primary SORA key")).not.toBe("preliminary");
    expect(evidenceByLabel.get("Primary banking key")).not.toBe("preliminary");

    const markdownResult = await handleMacroBrief({
      currency: "USD",
      format: "markdown",
    });
    expectMarkdownSections(markdownResult.content[0]?.text ?? "");
  });

  it("returns the expanded transport brief envelope", async () => {
    vi.mocked(getBusArrivals).mockResolvedValue([
      {
        busStopCode: "83139",
        serviceNo: "851",
        arrivals: [{ estimatedArrival: "2026-03-26T08:05:00+08:00" }],
      },
    ] as never);
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [{ line: "NSL" }],
      messages: [{ content: "Minor delay", createdDate: "2026-03-26T08:00:00+08:00" }],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([
      { type: "Road Works" },
    ] as never);

    const jsonResult = await handleTransportBrief({
      busStopCode: "83139",
      serviceNo: "851",
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");

    expect(payload.title).toBe("Transport Brief");
    expect(payload.provenance).toHaveLength(3);
    expect(payload.summary.some((item) => item.label === "Next bus ETA")).toBe(true);
    expect((payload.records["opsStatus"] as Record<string, unknown>)["level"]).toBe("disrupted");
    expect(payload.records["signals"]).toBeDefined();
    expect(payload.records["nextChecks"]).toBeDefined();

    const markdownResult = await handleTransportBrief({
      busStopCode: "83139",
      serviceNo: "851",
      format: "markdown",
    });
    expectMarkdownSections(markdownResult.content[0]?.text ?? "");
  });

  it("returns advisory transport status when only traffic incidents are active", async () => {
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [],
      messages: [],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([
      { type: "Accident" },
    ] as never);

    const jsonResult = await handleTransportBrief({
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");
    const opsStatus = payload.records["opsStatus"] as Record<string, unknown>;

    expect(opsStatus["level"]).toBe("advisory");
    expect(opsStatus["focus"]).toBe("network-wide");
  });

  it("returns unknown transport status when a requested bus stop has no ETA and no broader signals", async () => {
    vi.mocked(getBusArrivals).mockResolvedValue([
      {
        busStopCode: "83139",
        serviceNo: "851",
        arrivals: [{ estimatedArrival: null }],
      },
    ] as never);
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [],
      messages: [],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([] as never);

    const jsonResult = await handleTransportBrief({
      busStopCode: "83139",
      serviceNo: "851",
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");
    const opsStatus = payload.records["opsStatus"] as Record<string, unknown>;
    const nextChecks = payload.records["nextChecks"] as readonly Record<string, unknown>[];

    expect(opsStatus["level"]).toBe("unknown");
    expect(nextChecks.map((check) => check["tool"])).toEqual([
      "sg_lta_bus_arrivals",
      "sg_lta_train_alerts",
      "sg_lta_traffic_incidents",
    ]);
    expect((nextChecks[0]?.["input"] as Record<string, unknown>)["busStopCode"]).toBe("83139");
    expect((nextChecks[0]?.["input"] as Record<string, unknown>)["serviceNo"]).toBe("851");
  });

  it("returns normal transport status when the requested stop has arrivals and no disruptions", async () => {
    vi.mocked(getBusArrivals).mockResolvedValue([
      {
        busStopCode: "83139",
        serviceNo: "851",
        arrivals: [{ estimatedArrival: "2026-03-26T08:05:00+08:00" }],
      },
    ] as never);
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [],
      messages: [],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([] as never);

    const jsonResult = await handleTransportBrief({
      busStopCode: "83139",
      serviceNo: "851",
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");
    const opsStatus = payload.records["opsStatus"] as Record<string, unknown>;

    expect(opsStatus["level"]).toBe("normal");
    expect(opsStatus["focus"]).toBe("bus stop 83139 service 851");
  });

  it("returns the expanded environment brief envelope", async () => {
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Tampines",
        forecast: "Partly Cloudy",
        updatedAt: "2026-03-26T08:00:00+08:00",
        validFrom: "2026-03-26T08:00:00+08:00",
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
        stationName: "Tampines",
        value: 0.2,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");

    expect(payload.title).toBe("Environment Brief");
    expect(payload.provenance).toHaveLength(3);
    expect(payload.summary.some((item) => item.label === "PSI 24h")).toBe(true);
    expect((payload.records["opsStatus"] as Record<string, unknown>)["level"]).toBe("watch");
    expect(payload.records["thresholds"]).toBeDefined();
    expect(payload.records["signals"]).toBeDefined();
    expect(payload.records["nextChecks"]).toBeDefined();

    const markdownResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "markdown",
    });
    expectMarkdownSections(markdownResult.content[0]?.text ?? "");
  });

  it("returns caution environment status for thundery or heavy-rain forecasts", async () => {
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Tampines",
        forecast: "Thundery Showers",
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
        value: 0,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");

    expect((payload.records["opsStatus"] as Record<string, unknown>)["level"]).toBe("caution");
    expect((payload.records["thresholds"] as Record<string, unknown>)["forecastRisk"]).toBe("caution");
  });

  it("returns watch environment status for moderate PSI with no rain", async () => {
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
        psi24h: 75,
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getRainfall).mockResolvedValue([
      {
        stationId: "S107",
        stationName: "Tampines",
        value: 0,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");
    const nextChecks = payload.records["nextChecks"] as readonly Record<string, unknown>[];

    expect((payload.records["opsStatus"] as Record<string, unknown>)["level"]).toBe("watch");
    expect((payload.records["thresholds"] as Record<string, unknown>)["airQualityBand"]).toBe("watch");
    expect((nextChecks[0]?.["input"] as Record<string, unknown>)["area"]).toBe("Tampines");
    expect((nextChecks[1]?.["input"] as Record<string, unknown>)["region"]).toBe("East");
    expect((nextChecks[2]?.["input"] as Record<string, unknown>)["stationId"]).toBe("S107");
  });

  it("returns clear environment status when forecast, air quality, and rainfall are all clear", async () => {
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
        value: 0,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");

    expect((payload.records["opsStatus"] as Record<string, unknown>)["level"]).toBe("clear");
    expect((payload.records["thresholds"] as Record<string, unknown>)["rainfallBand"]).toBe("clear");
  });

  it("returns unknown environment status when all upstream reads fail", async () => {
    vi.mocked(getForecast2Hr).mockRejectedValue(new Error("forecast unavailable"));
    vi.mocked(getAirQuality).mockRejectedValue(new Error("air unavailable"));
    vi.mocked(getRainfall).mockRejectedValue(new Error("rainfall unavailable"));

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(jsonResult.content[0]?.text ?? "");

    expect((payload.records["opsStatus"] as Record<string, unknown>)["level"]).toBe("unknown");
    expect(payload.gaps).toHaveLength(3);
    expect(payload.records["signals"]).toEqual([]);
  });
});
