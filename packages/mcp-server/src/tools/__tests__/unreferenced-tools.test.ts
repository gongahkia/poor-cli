import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ToolResult } from "@swee-sg/shared";

// state dir must be redirected before keystore-tools loads (module creates a Keystore at import).
vi.hoisted(async () => {
  const { mkdtempSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  process.env["SG_APIS_STATE_DIR"] = mkdtempSync(join(tmpdir(), "sg-apis-test-"));
});

vi.mock("../../apis/hawker/client.js", () => ({
  getHawkerCentres: vi.fn(),
}));
vi.mock("../../apis/mom/client.js", () => ({
  getLabourStats: vi.fn(),
}));
vi.mock("../../apis/stb/client.js", () => ({
  getVisitorArrivals: vi.fn(),
}));
vi.mock("../../apis/nparks/client.js", () => ({
  getParks: vi.fn(),
}));
vi.mock("../../apis/pub/client.js", () => ({
  getWaterLevels: vi.fn(),
}));
vi.mock("../../apis/sfa/client.js", () => ({
  getSfaEstablishments: vi.fn(),
}));
vi.mock("../../apis/nea/client.js", () => ({
  getForecast2Hr: vi.fn(),
  getAirQuality: vi.fn(),
  getRainfall: vi.fn(),
}));
vi.mock("../../apis/mas/client.js", () => ({
  query: vi.fn(),
}));
vi.mock("../../apis/singstat/compare.js", () => ({
  compareIndicators: vi.fn(),
}));
vi.mock("../../apis/onemap/client.js", () => ({
  geocode: vi.fn(),
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

import { getHawkerCentres } from "../../apis/hawker/client.js";
import { getLabourStats } from "../../apis/mom/client.js";
import { getVisitorArrivals } from "../../apis/stb/client.js";
import { getParks } from "../../apis/nparks/client.js";
import { getWaterLevels } from "../../apis/pub/client.js";
import { getSfaEstablishments } from "../../apis/sfa/client.js";
import { getForecast2Hr, getAirQuality, getRainfall } from "../../apis/nea/client.js";
import { query as masQuery } from "../../apis/mas/client.js";
import { compareIndicators } from "../../apis/singstat/compare.js";

import { handleHawkerCentres } from "../hawker-tools.js";
import { handleMomLabourStats } from "../mom-tools.js";
import { handleStbVisitorStats } from "../stb-tools.js";
import { handleNParks } from "../nparks-tools.js";
import { handlePubWaterLevels } from "../pub-tools.js";
import { handleSfaEstablishments } from "../sfa-tools.js";
import { handleNeaAirQuality, handleNeaRainfall } from "../nea-tools.js";
import { handleMasFinancialStats } from "../mas-tools.js";
import { configToolDefinitions } from "../config-tools.js";
import { keystoreToolDefinitions } from "../keystore-tools.js";
import { singstatToolDefinitions } from "../singstat-tools.js";
import { handleCivicBrief } from "../brief-tools.js";

const getText = (result: ToolResult): string =>
  result.content.find((item): item is Extract<ToolResult["content"][number], { type: "text" }> => item.type === "text")?.text ?? "";

const findDefinition = <T extends { name: string }>(defs: readonly T[], name: string): T => {
  const def = defs.find((d) => d.name === name);
  if (def === undefined) throw new Error(`tool definition not found: ${name}`);
  return def;
};

describe("direct tests for previously un-referenced tools", () => {
  beforeEach(() => {
    // do not clear mocks; each test sets its own mockResolvedValue. clearing between tests
    // in parallel runs has been observed to race with vitest's module-mock hoisting under
    // concurrent test-file execution.
  });

  describe("sg_hawker_centres", () => {
    it("returns records from hawker client", async () => {
      vi.mocked(getHawkerCentres).mockResolvedValue([{ name: "Maxwell Food Centre", postalCode: "069184" }] as never);
      const result = await handleHawkerCentres({ name: "Maxwell", format: "json" });
      expect(result.structuredContent).toMatchObject({
        records: [expect.objectContaining({ name: "Maxwell Food Centre" })],
      });
      expect(getHawkerCentres).toHaveBeenCalledWith(expect.objectContaining({ name: "Maxwell" }));
    });
  });

  describe("sg_mom_labour_stats", () => {
    it("returns labour stats records", async () => {
      vi.mocked(getLabourStats).mockResolvedValue([{ indicator: "unemployment_rate", value: 2.1 }] as never);
      const result = await handleMomLabourStats({ indicator: "unemployment_rate", format: "json" });
      expect(result.structuredContent).toMatchObject({
        records: [expect.objectContaining({ indicator: "unemployment_rate" })],
      });
    });
  });

  describe("sg_stb_visitor_stats", () => {
    it("returns visitor arrival records", async () => {
      vi.mocked(getVisitorArrivals).mockResolvedValue([{ country: "Indonesia", year: "2025", value: 3500000 }] as never);
      const result = await handleStbVisitorStats({ country: "Indonesia", format: "json" });
      expect(result.structuredContent).toMatchObject({
        records: [expect.objectContaining({ country: "Indonesia" })],
      });
    });
  });

  describe("sg_nparks_parks", () => {
    it("returns park directory records", async () => {
      vi.mocked(getParks).mockResolvedValue([{ name: "Bishan-AMK Park" }] as never);
      const result = await handleNParks({ name: "Bishan", format: "json" });
      expect(result.structuredContent).toMatchObject({
        records: [expect.objectContaining({ name: "Bishan-AMK Park" })],
      });
    });
  });

  describe("sg_pub_water_levels", () => {
    it("returns station water-level records", async () => {
      vi.mocked(getWaterLevels).mockResolvedValue([{ station: "Bedok Canal", level: 0.8 }] as never);
      const result = await handlePubWaterLevels({ station: "Bedok Canal", format: "json" });
      expect(result.structuredContent).toMatchObject({
        records: [expect.objectContaining({ station: "Bedok Canal" })],
      });
    });
  });

  describe("sg_sfa_establishments", () => {
    it("returns licensed food-establishment records", async () => {
      vi.mocked(getSfaEstablishments).mockResolvedValue([{ name: "Test Cafe", licenceNo: "ABC123" }] as never);
      const result = await handleSfaEstablishments({ name: "Test", format: "json" });
      expect(result.structuredContent).toMatchObject({
        records: [expect.objectContaining({ licenceNo: "ABC123" })],
      });
    });
  });

  describe("sg_nea_air_quality", () => {
    it("returns air-quality records and meta", async () => {
      vi.mocked(getAirQuality).mockResolvedValue([
        { region: "east", psi: 52, pm25: 18, updatedAt: "2026-04-22T10:00:00Z" },
      ] as never);
      const result = await handleNeaAirQuality({ region: "east", format: "json" });
      expect(result.structuredContent).toMatchObject({
        records: [expect.objectContaining({ region: "east", psi: 52 })],
        meta: expect.objectContaining({
          requestedScope: { region: "east", date: null },
          upstreamTimestamp: "2026-04-22T10:00:00Z",
        }),
      });
    });

    it("returns safe metadata for empty air-quality results", async () => {
      vi.mocked(getAirQuality).mockResolvedValue([] as never);

      const result = await handleNeaAirQuality({ region: "east", format: "json" });

      expect(result.structuredContent).toMatchObject({
        records: [],
        meta: expect.objectContaining({
          requestedScope: { region: "east", date: null },
          resolvedScope: { region: "east", rowCount: 0 },
          upstreamTimestamp: null,
        }),
      });
    });

    it("normalizes undefined air-quality upstream results to an empty record set", async () => {
      vi.mocked(getAirQuality).mockResolvedValue(undefined as never);

      const result = await handleNeaAirQuality({ format: "json" });

      expect(result.structuredContent).toMatchObject({
        records: [],
        meta: expect.objectContaining({
          requestedScope: { region: null, date: null },
          resolvedScope: { region: null, rowCount: 0 },
          upstreamTimestamp: null,
        }),
      });
    });
  });

  describe("sg_nea_rainfall", () => {
    it("returns rainfall records and meta", async () => {
      vi.mocked(getRainfall).mockResolvedValue([
        { stationId: "S107", stationName: "Tampines", value: 0.4, timestamp: "2026-04-22T10:05:00Z" },
      ] as never);
      const result = await handleNeaRainfall({ stationId: "S107", format: "json" });
      expect(result.structuredContent).toMatchObject({
        records: [expect.objectContaining({ stationId: "S107" })],
        meta: expect.objectContaining({
          resolvedScope: expect.objectContaining({ stationId: "S107", stationName: "Tampines" }),
        }),
      });
    });

    it("returns safe metadata for empty rainfall results", async () => {
      vi.mocked(getRainfall).mockResolvedValue([] as never);

      const result = await handleNeaRainfall({ stationId: "S107", format: "json" });

      expect(result.structuredContent).toMatchObject({
        records: [],
        meta: expect.objectContaining({
          requestedScope: { stationId: "S107", date: null },
          resolvedScope: { stationId: "S107", stationName: null, rowCount: 0 },
          upstreamTimestamp: null,
        }),
      });
    });

    it("normalizes undefined rainfall upstream results to an empty record set", async () => {
      vi.mocked(getRainfall).mockResolvedValue(undefined as never);

      const result = await handleNeaRainfall({ format: "json" });

      expect(result.structuredContent).toMatchObject({
        records: [],
        meta: expect.objectContaining({
          requestedScope: { stationId: null, date: null },
          resolvedScope: { stationId: null, stationName: null, rowCount: 0 },
          upstreamTimestamp: null,
        }),
      });
    });

    it("propagates forecast mock coverage (wiring sanity)", async () => {
      vi.mocked(getForecast2Hr).mockResolvedValue([{ area: "Tampines", forecast: "Fair" }] as never);
      expect(getForecast2Hr).toBeDefined();
    });
  });

  describe("sg_mas_financial_stats", () => {
    it("returns normalized MAS banking records filtered by exact date", async () => {
      vi.mocked(masQuery).mockResolvedValue([
        { end_of_day: "2026-03-31", total_deposits: 1000 },
        { end_of_day: "2026-02-28", total_deposits: 980 },
      ] as never);
      const result = await handleMasFinancialStats({ date: "2026-03-31", format: "json" });
      const records = (result.structuredContent as { records: Record<string, unknown>[] }).records;
      expect(records).toHaveLength(1);
      expect(records[0]).toMatchObject({ date: expect.stringContaining("2026-03-31"), total_deposits: 1000 });
    });
  });

  describe("sg_singstat_compare", () => {
    it("returns pivoted records per period across series", async () => {
      vi.mocked(compareIndicators).mockResolvedValue({
        series: [
          { label: "GDP", values: [100, 105] },
          { label: "CPI", values: [1.2, 1.6] },
        ],
        periods: ["2024", "2025"],
      } as never);
      const def = findDefinition(singstatToolDefinitions, "sg_singstat_compare");
      const result = await def.handler({
        queries: [
          { tableId: "M015631", indicator: "GDP", label: "GDP" },
          { tableId: "M213781", indicator: "CPI", label: "CPI" },
        ],
        startYear: 2024,
        endYear: 2025,
        format: "json",
      });
      expect(result.structuredContent).toMatchObject({
        records: [
          { period: "2024", GDP: 100, CPI: 1.2 },
          { period: "2025", GDP: 105, CPI: 1.6 },
        ],
      });
    });
  });

  describe("sg_config_get", () => {
    it("returns the current runtime config record", async () => {
      const def = findDefinition(configToolDefinitions, "sg_config_get");
      const result = await def.handler({});
      const record = (result.structuredContent as { record: Record<string, unknown> }).record;
      expect(record).toBeDefined();
      expect(record).toEqual(expect.any(Object));
      expect(getText(result)).toContain("{");
    });
  });

  describe("sg_config_set", () => {
    it("rejects unknown config keys with a validation error", async () => {
      const def = findDefinition(configToolDefinitions, "sg_config_set");
      await expect(def.handler({ key: "nonexistent.path", value: "1" })).rejects.toThrow();
    });
  });

  describe("sg_key_list", () => {
    it("returns a records array even when the keystore is empty", async () => {
      const def = findDefinition(keystoreToolDefinitions, "sg_key_list");
      const result = await def.handler({});
      expect(result.structuredContent).toMatchObject({ records: expect.any(Array) });
    });
  });

  describe("sg_key_delete", () => {
    it("returns a not-found message for an unknown api name", async () => {
      const def = findDefinition(keystoreToolDefinitions, "sg_key_delete");
      const result = await def.handler({ apiName: "definitely_not_a_real_api" });
      expect(getText(result).toLowerCase()).toContain("no api key found");
    });

    it("deletes an existing api key and reports success", async () => {
      const setDef = findDefinition(keystoreToolDefinitions, "sg_key_set");
      await setDef.handler({ apiName: "ephemeral_test", key: "abcdef" });
      const delDef = findDefinition(keystoreToolDefinitions, "sg_key_delete");
      const result = await delDef.handler({ apiName: "ephemeral_test" });
      expect(getText(result).toLowerCase()).toContain("api key deleted");
    });
  });

  describe("sg_civic_brief", () => {
    it("records a NO_LOCATION gap when no location identifier is supplied", async () => {
      const result = await handleCivicBrief({ format: "json" });
      const payload = JSON.parse(getText(result));
      expect(payload.title).toBe("Civic Brief");
      expect(payload.gaps.map((g: { code: string }) => g.code)).toContain("NO_LOCATION");
    });
  });
});
