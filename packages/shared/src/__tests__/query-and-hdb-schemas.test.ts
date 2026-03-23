import { describe, expect, it } from "vitest";
import {
  AcraEntitiesSchema,
  BcaLicensedBuildersSchema,
  BcaRegisteredContractorsSchema,
  CeaSalespersonsSchema,
  HdbRentalPricesSchema,
  HdbResalePricesSchema,
  OneMapRouteSchema,
  QuerySchema,
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
});
