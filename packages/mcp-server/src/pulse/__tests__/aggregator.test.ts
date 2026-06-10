import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildPulseMobilitySnapshot, buildPulseWeatherSnapshot, explainPulseSnapshot } from "../aggregator.js";
import { getTrafficIncidents, getTrainAlerts, getRoadWorks, getRoadOpenings, getTrafficImages } from "../../apis/lta/client.js";
import { getForecast2Hr, getAirQuality, getRainfall } from "../../apis/nea/client.js";

vi.mock("../../apis/lta/client.js", () => ({
  getTrafficIncidents: vi.fn(),
  getTrainAlerts: vi.fn(),
  getRoadWorks: vi.fn(),
  getRoadOpenings: vi.fn(),
  getTrafficImages: vi.fn(),
}));

vi.mock("../../apis/nea/client.js", () => ({
  getForecast2Hr: vi.fn(),
  getAirQuality: vi.fn(),
  getRainfall: vi.fn(),
}));

const mocked = <T extends (...args: never[]) => unknown>(fn: T) => vi.mocked(fn);

describe("Swee Pulse aggregators", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("returns deterministic weather signals and source freshness", async () => {
    mocked(getForecast2Hr).mockResolvedValue([{
      area: "Bedok",
      forecast: "Thundery Showers",
      validFrom: "2026-05-22T07:00:00.000Z",
      validTo: "2026-05-22T09:00:00.000Z",
      validText: "7 AM - 9 AM",
      updatedAt: "2026-05-22T06:58:00.000Z",
      lat: 1.32,
      lng: 103.93,
    }]);
    mocked(getAirQuality).mockResolvedValue([{
      region: "east",
      psi24h: 40,
      pm25OneHourly: 12,
      pm25TwentyFourHourly: 10,
      updatedAt: "2026-05-22T06:58:00.000Z",
      lat: 1.35,
      lng: 103.94,
    }]);
    mocked(getRainfall).mockResolvedValue([{
      stationId: "S1",
      stationName: "Station 1",
      value: 12,
      unit: "mm",
      timestamp: "2026-05-22T06:58:00.000Z",
      lat: 1.3,
      lng: 103.8,
    }]);

    const result = await buildPulseWeatherSnapshot({ area: "Bedok" });

    expect(result.signals.map((signal) => signal.sourceTool)).toEqual([
      "sg_nea_forecast_2hr",
      "sg_nea_air_quality",
      "sg_nea_rainfall",
    ]);
    expect(result.signals.map((signal) => signal.severity)).toEqual(["watch", "info", "disrupted"]);
    expect(result.sourceHealth).toHaveLength(3);
    expect(result.gaps).toEqual([]);
  });

  it("returns mobility gaps when credentialed LTA sources are unavailable", async () => {
    mocked(getTrafficIncidents).mockRejectedValue(new Error("LTA key missing"));
    mocked(getTrainAlerts).mockResolvedValue({ alerts: [], messages: [] });
    mocked(getRoadWorks).mockResolvedValue([]);
    mocked(getRoadOpenings).mockResolvedValue([]);
    mocked(getTrafficImages).mockResolvedValue([]);

    const result = await buildPulseMobilitySnapshot();

    expect(result.gaps[0]?.code).toBe("SG_LTA_TRAFFIC_INCIDENTS_FAILED");
    expect(result.sourceHealth.some((source) => source.status === "gap")).toBe(true);
  });

  it("returns mobility signals and source health when LTA sources respond", async () => {
    mocked(getTrafficIncidents).mockResolvedValue([{
      type: "Accident",
      message: "Accident on CTE toward city.",
      lat: 1.31,
      lng: 103.84,
    }]);
    mocked(getTrainAlerts).mockResolvedValue({
      alerts: [{ line: "EWL", status: 1, direction: null, stations: [], freePublicBus: [], freeMrtShuttle: [], mrtShuttleDirection: null }],
      messages: [{ content: "All clear", createdDate: "2026-05-22T06:58:00.000Z" }],
    });
    mocked(getRoadWorks).mockResolvedValue([{ id: "rw-1", eventType: "road-work", lat: null, lng: null, roadName: "PIE", message: "Road works", startTime: "2026-05-22T07:00:00.000Z", endTime: null }]);
    mocked(getRoadOpenings).mockResolvedValue([{ id: "ro-1", eventType: "road-opening", lat: null, lng: null, roadName: "TPE", message: "Road opening", startTime: "2026-05-22T08:00:00.000Z", endTime: null }]);
    mocked(getTrafficImages).mockResolvedValue([{ cameraId: "1701", imageUrl: "https://example.test/traffic.jpg", timestamp: "2026-05-22T06:58:00.000Z", lat: 1.3, lng: 103.8 }]);

    const result = await buildPulseMobilitySnapshot();

    expect(result.signals.map((signal) => signal.sourceTool)).toEqual([
      "sg_lta_traffic_incidents",
      "sg_lta_train_alerts",
      "sg_lta_road_works",
      "sg_lta_road_openings",
    ]);
    expect(result.signals.find((signal) => signal.sourceTool === "sg_lta_road_works")).toMatchObject({
      severity: "watch",
      title: "PIE: road work",
    });
    expect(result.sourceHealth).toHaveLength(5);
    expect(result.gaps).toEqual([]);
  });

  it("surfaces empty weather source gaps without inventing signals", async () => {
    mocked(getForecast2Hr).mockResolvedValue([]);
    mocked(getAirQuality).mockResolvedValue([]);
    mocked(getRainfall).mockResolvedValue([]);

    const result = await buildPulseWeatherSnapshot();

    expect(result.signals).toEqual([]);
    expect(result.gaps.map((gap) => gap.code)).toEqual([
      "NEA_FORECAST_EMPTY",
      "NEA_AIR_QUALITY_EMPTY",
      "NEA_RAINFALL_EMPTY",
    ]);
  });

  it("surfaces weather upstream failures as source-health gaps", async () => {
    mocked(getForecast2Hr).mockRejectedValue(new Error("NEA offline"));
    mocked(getAirQuality).mockResolvedValue([]);
    mocked(getRainfall).mockResolvedValue([]);

    const result = await buildPulseWeatherSnapshot();

    expect(result.gaps[0]?.code).toBe("SG_NEA_FORECAST_2HR_FAILED");
    expect(result.sourceHealth[0]).toMatchObject({
      sourceTool: "sg_nea_forecast_2hr",
      status: "gap",
      recordCount: 0,
    });
  });

  it("explains snapshots without AI", () => {
    expect(explainPulseSnapshot({
      generatedAt: "2026-05-22T07:00:00.000Z",
      focus: null,
      signals: [],
      sourceHealth: [],
      gaps: [],
    })).toContain("0 source-backed signals");
  });
});
