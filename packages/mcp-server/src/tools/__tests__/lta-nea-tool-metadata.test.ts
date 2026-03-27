import { beforeEach, describe, expect, it, vi } from "vitest";

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

import { getBusArrivals, getTrafficIncidents, getTrainAlerts } from "../../apis/lta/client.js";
import { getAirQuality, getForecast2Hr, getRainfall } from "../../apis/nea/client.js";
import {
  handleLtaBusArrivals,
  handleLtaTrafficIncidents,
  handleLtaTrainAlerts,
} from "../lta-tools.js";
import {
  handleNeaAirQuality,
  handleNeaForecast2Hr,
  handleNeaRainfall,
} from "../nea-tools.js";

describe("LTA and NEA direct-tool metadata", () => {
  beforeEach(() => {
    vi.mocked(getBusArrivals).mockReset();
    vi.mocked(getTrainAlerts).mockReset();
    vi.mocked(getTrafficIncidents).mockReset();
    vi.mocked(getForecast2Hr).mockReset();
    vi.mocked(getAirQuality).mockReset();
    vi.mocked(getRainfall).mockReset();
  });

  it("adds structured metadata to bus arrivals", async () => {
    vi.mocked(getBusArrivals).mockResolvedValue([
      {
        busStopCode: "83139",
        serviceNo: "851",
        operator: "SBST",
        arrivals: [{ estimatedArrival: "2099-03-26T08:05:00+08:00" }],
      },
    ] as never);

    const result = await handleLtaBusArrivals({ busStopCode: "83139", serviceNo: "851", format: "json" });

    expect(result.structuredContent).toMatchObject({
      meta: {
        requestedScope: { busStopCode: "83139", serviceNo: "851" },
        resolvedScope: { busStopCode: "83139", serviceNo: "851", serviceCount: 1 },
        upstreamTimestamp: "2099-03-26T08:05:00+08:00",
        coverage: expect.stringContaining("Stop-level bus arrival timings"),
      },
    });
    expect((result.structuredContent?.["meta"] as Record<string, unknown>)["observedAt"]).toEqual(expect.any(String));
  });

  it("adds structured metadata to train alerts", async () => {
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [{ line: "NSL" }],
      messages: [{ content: "Minor delay", createdDate: "2026-03-26T08:00:00+08:00" }],
    } as never);

    const result = await handleLtaTrainAlerts({ format: "json" });

    expect(result.structuredContent).toMatchObject({
      meta: {
        requestedScope: { networkWide: true },
        resolvedScope: { networkWide: true, lines: ["NSL"], alertCount: 1, messageCount: 1 },
        upstreamTimestamp: "2026-03-26T08:00:00+08:00",
      },
    });
  });

  it("adds structured metadata to traffic incidents", async () => {
    vi.mocked(getTrafficIncidents).mockResolvedValue([
      { type: "Road Works", message: "Road works on PIE" },
    ] as never);

    const result = await handleLtaTrafficIncidents({ format: "json" });

    expect(result.structuredContent).toMatchObject({
      meta: {
        requestedScope: { networkWide: true },
        resolvedScope: { networkWide: true, incidentCount: 1, incidentTypes: ["Road Works"] },
        upstreamTimestamp: null,
      },
    });
  });

  it("adds structured metadata to forecast rows", async () => {
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Tampines",
        forecast: "Partly Cloudy",
        validFrom: "2026-03-26T08:00:00+08:00",
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const result = await handleNeaForecast2Hr({ area: "Tampines", format: "json" });

    expect(result.structuredContent).toMatchObject({
      meta: {
        requestedScope: { area: "Tampines", date: null },
        resolvedScope: { area: "Tampines", rowCount: 1 },
        upstreamTimestamp: "2026-03-26T08:00:00+08:00",
      },
    });
  });

  it("adds structured metadata to air-quality rows", async () => {
    vi.mocked(getAirQuality).mockResolvedValue([
      {
        region: "East",
        psi24h: 42,
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const result = await handleNeaAirQuality({ region: "East", format: "json" });

    expect(result.structuredContent).toMatchObject({
      meta: {
        requestedScope: { region: "East", date: null },
        resolvedScope: { region: "East", rowCount: 1 },
        upstreamTimestamp: "2026-03-26T08:00:00+08:00",
      },
    });
  });

  it("adds structured metadata to rainfall rows", async () => {
    vi.mocked(getRainfall).mockResolvedValue([
      {
        stationId: "S107",
        stationName: "Tampines West",
        value: 0.4,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const result = await handleNeaRainfall({ stationId: "S107", format: "json" });

    expect(result.structuredContent).toMatchObject({
      meta: {
        requestedScope: { stationId: "S107", date: null },
        resolvedScope: { stationId: "S107", stationName: "Tampines West", rowCount: 1 },
        upstreamTimestamp: "2026-03-26T08:00:00+08:00",
      },
    });
  });
});
