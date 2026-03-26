import { describe, expect, it } from "vitest";
import {
  AcraEntitiesSchema,
  BcaLicensedBuildersSchema,
  BcaRegisteredContractorsSchema,
  BriefArtifactSchema,
  BusinessDossierSchema,
  CeaSalespersonsSchema,
  DatagovResourcesSchema,
  DatagovRowsSchema,
  EnvironmentBriefSchema,
  HdbRentalPricesSchema,
  HdbResalePricesSchema,
  MacroBriefSchema,
  OneMapRouteSchema,
  PropertyBriefSchema,
  QuerySchema,
  TransportBriefSchema,
} from "../schemas/index.js";

describe("query and HDB schema contracts", () => {
  it("accepts sg_query plan mode", () => {
    expect(
      QuerySchema.safeParse({
        query: "Macro snapshot of Singapore",
        mode: "plan",
      }).success,
    ).toBe(true);
  });

  it("rejects unsupported sg_query fields", () => {
    expect(
      QuerySchema.safeParse({
        query: "Macro snapshot of Singapore",
        depth: "high",
      }).success,
    ).toBe(false);
  });

  it("accepts bounded HDB resale filters", () => {
    expect(
      HdbResalePricesSchema.safeParse({
        town: "Bedok",
        flatType: "4 ROOM",
        startMonth: "2026-01",
        endMonth: "2026-03",
        limit: 20,
      }).success,
    ).toBe(true);
  });

  it("rejects malformed HDB month filters", () => {
    expect(
      HdbRentalPricesSchema.safeParse({
        startMonth: "2026/01",
      }).success,
    ).toBe(false);
  });

  it("rejects unsupported OneMap route fields", () => {
    expect(
      OneMapRouteSchema.safeParse({
        startLat: 1.3,
        startLng: 103.8,
        endLat: 1.31,
        endLng: 103.81,
        routeType: "drive",
        date: "2026-03-24",
      }).success,
    ).toBe(false);
  });

  it("requires at least one exact-match filter for CEA lookups", () => {
    expect(
      CeaSalespersonsSchema.safeParse({
        limit: 10,
      }).success,
    ).toBe(false);
  });

  it("accepts bounded BCA direct-tool filters", () => {
    expect(
      BcaLicensedBuildersSchema.safeParse({
        companyName: "ABC CONSTRUCTION PTE LTD",
        limit: 10,
      }).success,
    ).toBe(true);
    expect(
      BcaRegisteredContractorsSchema.safeParse({
        workhead: "CW01",
        grade: "C3",
      }).success,
    ).toBe(true);
  });

  it("requires an entity name or UEN for ACRA lookups", () => {
    expect(
      AcraEntitiesSchema.safeParse({
        limit: 5,
      }).success,
    ).toBe(false);
    expect(
      AcraEntitiesSchema.safeParse({
        entityName: "ABC CONSTRUCTION PTE LTD",
      }).success,
    ).toBe(true);
  });

  it("accepts dataset resource inspection and bounded row reads", () => {
    expect(
      DatagovResourcesSchema.safeParse({
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        format: "json",
      }).success,
    ).toBe(true);
    expect(
      DatagovRowsSchema.safeParse({
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        filters: {
          town: "BEDOK",
          floor_area_sqm: 92,
          active: true,
        },
        limit: 20,
        offset: 0,
        sort: "month desc",
      }).success,
    ).toBe(true);
  });

  it("requires a datasetId or resourceId for data.gov row reads", () => {
    expect(
      DatagovRowsSchema.safeParse({
        limit: 10,
      }).success,
    ).toBe(false);
  });

  it("accepts bounded additive brief schemas", () => {
    expect(
      BusinessDossierSchema.safeParse({
        entityName: "ABC CONSTRUCTION PTE LTD",
        workhead: "CW01",
        format: "markdown",
      }).success,
    ).toBe(true);
    expect(
      PropertyBriefSchema.safeParse({
        postalCode: "168742",
        includeEnvironment: true,
        format: "json",
      }).success,
    ).toBe(true);
    expect(
      MacroBriefSchema.safeParse({
        currency: "USD",
        startDate: "2025-01-01",
        endDate: "2025-01-31",
      }).success,
    ).toBe(true);
    expect(
      TransportBriefSchema.safeParse({
        busStopCode: "83139",
        serviceNo: "851",
        format: "json",
      }).success,
    ).toBe(true);
    expect(
      EnvironmentBriefSchema.safeParse({
        area: "Tampines",
        region: "East",
        stationId: "S107",
        format: "markdown",
      }).success,
    ).toBe(true);
  });

  it("rejects empty additive briefs", () => {
    expect(
      BusinessDossierSchema.safeParse({
        format: "json",
      }).success,
    ).toBe(false);
    expect(
      PropertyBriefSchema.safeParse({
        includeTransport: true,
      }).success,
    ).toBe(false);
    expect(
      TransportBriefSchema.safeParse({
        serviceNo: "851",
      }).success,
    ).toBe(false);
  });

  it("accepts the expanded brief artifact envelope", () => {
    expect(
      BriefArtifactSchema.safeParse({
        title: "Macro Brief",
        summary: [{ label: "USD/SGD", value: 1.35, source: "MAS" }],
        evidence: [{ label: "FX rows", value: 1, source: "MAS" }],
        records: { exchangeRates: [] },
        gaps: [{ code: "NONE", message: "No gaps." }],
        provenance: [{
          source: "MAS",
          tool: "sg_mas_exchange_rates",
          coverage: "Exchange-rate coverage.",
          authRequired: false,
          recordCount: 1,
        }],
        freshness: [{
          source: "MAS",
          observedAt: "2026-03-26T00:00:00.000Z",
          upstreamTimestamp: "2026-03-26",
        }],
        limits: [{ code: "SNAPSHOT_ONLY", message: "Starter brief only." }],
      }).success,
    ).toBe(true);
  });
});
