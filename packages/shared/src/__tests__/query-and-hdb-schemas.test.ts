import { describe, expect, it } from "vitest";
import {
  HdbRentalPricesSchema,
  HdbResalePricesSchema,
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
});
