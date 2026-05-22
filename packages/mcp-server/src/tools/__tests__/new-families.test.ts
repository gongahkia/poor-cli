import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ToolResult } from "@swee-sg/shared";

vi.mock("../../apis/coe/client.js", () => ({ getCoeBiddingResults: vi.fn() }));
vi.mock("../../apis/iras/client.js", () => ({ getIrasTaxCollection: vi.fn() }));
vi.mock("../../apis/spf/client.js", () => ({ getSpfCrimeStats: vi.fn() }));
vi.mock("../../apis/ema/client.js", () => ({ getEmaElectricityGeneration: vi.fn() }));
vi.mock("../../apis/lta/client.js", () => ({
  getCarparkAvailability: vi.fn(),
  getTaxiAvailability: vi.fn(),
  getBusArrivals: vi.fn(),
  getRoadOpenings: vi.fn(),
  getRoadWorks: vi.fn(),
  getTrafficImages: vi.fn(),
  getTrafficIncidents: vi.fn(),
  getTrainAlerts: vi.fn(),
}));

import { getCoeBiddingResults } from "../../apis/coe/client.js";
import { getIrasTaxCollection } from "../../apis/iras/client.js";
import { getSpfCrimeStats } from "../../apis/spf/client.js";
import { getEmaElectricityGeneration } from "../../apis/ema/client.js";
import { getCarparkAvailability, getTaxiAvailability } from "../../apis/lta/client.js";

import { handleLtaCoeResults } from "../coe-tools.js";
import { handleIrasTaxCollection } from "../iras-tools.js";
import { handleSpfCrimeStats } from "../spf-tools.js";
import { handleEmaElectricityGeneration } from "../ema-tools.js";
import { handleLtaCarparkAvailability, handleLtaTaxiAvailability } from "../lta-tools.js";

const records = (r: ToolResult): Record<string, unknown>[] =>
  (r.structuredContent as { records: Record<string, unknown>[] }).records;

describe("new data families (Bundle B1)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sg_lta_coe_results returns normalized records", async () => {
    vi.mocked(getCoeBiddingResults).mockResolvedValue([
      { month: "2026-03", biddingNo: "1", vehicleClass: "A", quota: 1000, bidsSuccess: 900, bidsReceived: 1200, premium: 92000 },
    ] as never);
    const result = await handleLtaCoeResults({ category: "A", format: "json" });
    expect(records(result)[0]).toMatchObject({ vehicleClass: "A", premium: 92000 });
  });

  it("sg_iras_tax_collection returns normalized records", async () => {
    vi.mocked(getIrasTaxCollection).mockResolvedValue([
      { financialYear: "FY2024", taxType: "Individual Income Tax", revenueSource: null, taxCollection: 16200000000 },
    ] as never);
    const result = await handleIrasTaxCollection({ financialYear: "FY2024", format: "json" });
    expect(records(result)[0]).toMatchObject({ financialYear: "FY2024", taxCollection: 16200000000 });
  });

  it("sg_spf_crime_stats returns normalized records", async () => {
    vi.mocked(getSpfCrimeStats).mockResolvedValue([
      { year: "2025", offenceCategory: "Outrage of Modesty", offence: "OOM", cases: 1500 },
    ] as never);
    const result = await handleSpfCrimeStats({ year: "2025", format: "json" });
    expect(records(result)[0]).toMatchObject({ year: "2025", cases: 1500 });
  });

  it("sg_ema_electricity_generation returns normalized records", async () => {
    vi.mocked(getEmaElectricityGeneration).mockResolvedValue([
      { year: "2026", month: "03", energyType: "Natural Gas", generationGwh: 4200.5 },
    ] as never);
    const result = await handleEmaElectricityGeneration({ year: "2026", format: "json" });
    expect(records(result)[0]).toMatchObject({ energyType: "Natural Gas", generationGwh: 4200.5 });
  });

  it("sg_lta_carpark_availability returns records with meta", async () => {
    vi.mocked(getCarparkAvailability).mockResolvedValue([
      { carparkId: "HE12", development: "Blk 123", area: "Hougang", availableLots: 42, lotType: "C", agency: "HDB", lat: 1.37, lng: 103.89 },
    ] as never);
    const result = await handleLtaCarparkAvailability({ development: "Blk 123", format: "json" });
    expect(records(result)[0]).toMatchObject({ carparkId: "HE12", availableLots: 42 });
    expect(result.structuredContent).toHaveProperty("meta");
  });

  it("sg_lta_taxi_availability returns positions with meta", async () => {
    vi.mocked(getTaxiAvailability).mockResolvedValue([
      { lat: 1.3, lng: 103.8 },
      { lat: 1.31, lng: 103.81 },
    ] as never);
    const result = await handleLtaTaxiAvailability({ format: "json" });
    expect(records(result)).toHaveLength(2);
    expect((result.structuredContent as { meta: { resolvedScope: { taxiCount: number } } }).meta.resolvedScope.taxiCount).toBe(2);
  });
});
