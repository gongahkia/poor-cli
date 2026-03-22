import { describe, expect, it } from "vitest";
import {
  MasExchangeRateSchema,
  MasFinancialStatsSchema,
  MasInterestRateSchema,
} from "../schemas/index.js";

describe("MAS schema contracts", () => {
  it("accepts exact-date exchange rate lookups", () => {
    expect(
      MasExchangeRateSchema.safeParse({
        currency: "USD",
        date: "2025-01-02",
      }).success,
    ).toBe(true);
  });

  it("rejects deprecated exchange-rate range fields", () => {
    expect(
      MasExchangeRateSchema.safeParse({
        startDate: "2025-01-01",
        endDate: "2025-01-02",
      }).success,
    ).toBe(false);
  });

  it("rejects unsupported interest-rate variants", () => {
    expect(
      MasInterestRateSchema.safeParse({
        rateType: "prime",
      }).success,
    ).toBe(false);
  });

  it("rejects unsupported financial-stat categories", () => {
    expect(
      MasFinancialStatsSchema.safeParse({
        category: "insurance",
      }).success,
    ).toBe(false);
  });
});
