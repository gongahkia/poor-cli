import { describe, expect, it } from "vitest";
import { computeAffordability } from "../affordability.js";
import type { HouseholdProfile } from "../grants.js";

const profile: HouseholdProfile = {
  applicants: [
    { age: 30, citizenship: "citizen", monthlyIncomeSgd: 5000, employmentMonths: 24, firstTimer: true },
    { age: 29, citizenship: "citizen", monthlyIncomeSgd: 4500, employmentMonths: 36, firstTimer: true },
  ],
  maritalStatus: "married",
  flatMode: "resale",
  flatSize: "4_room",
  proximityToParents: "near",
};

describe("computeAffordability", () => {
  it("returns fits verdict when within all caps", () => {
    const r = computeAffordability({
      profile,
      targetPriceSgd: 600000,
      tenureYears: 25,
      cashOnHandSgd: 100000,
      cpfOaBalanceSgd: 200000,
      loanType: "hdb",
    });
    expect(["fits", "tight"]).toContain(r.verdict);
    expect(r.recommendedLoanSgd).toBeGreaterThan(0);
    expect(r.recommendedLoanSgd).toBeLessThanOrEqual(r.maxLoanByLtvSgd);
  });

  it("LTV cap is 75% of price for HDB loan", () => {
    const r = computeAffordability({
      profile,
      targetPriceSgd: 600000,
      tenureYears: 25,
      cashOnHandSgd: 100000,
      cpfOaBalanceSgd: 200000,
      loanType: "hdb",
    });
    expect(r.maxLoanByLtvSgd).toBe(450000);
  });

  it("flags over_budget when cash insufficient", () => {
    const r = computeAffordability({
      profile,
      targetPriceSgd: 600000,
      tenureYears: 25,
      cashOnHandSgd: 0,
      cpfOaBalanceSgd: 200000,
      loanType: "bank",
    });
    expect(r.verdict).toBe("over_budget");
  });

  it("computes BSD residential tiers", () => {
    const r = computeAffordability({
      profile,
      targetPriceSgd: 600000,
      tenureYears: 25,
      cashOnHandSgd: 100000,
      cpfOaBalanceSgd: 200000,
    });
    // 1% of first 180k + 2% of next 180k + 3% of remaining 240k = 1800+3600+7200 = 12600
    expect(r.bsdSgd).toBe(12600);
  });

  it("nets grants against net cash outlay", () => {
    const r = computeAffordability({
      profile,
      targetPriceSgd: 600000,
      tenureYears: 25,
      cashOnHandSgd: 100000,
      cpfOaBalanceSgd: 200000,
    });
    expect(r.grants.totalSgd).toBeGreaterThan(0);
    expect(r.netCashOutlaySgd).toBeLessThan(r.downpayment.cashRequiredSgd + r.bsdSgd);
  });

  it("MSR utilization stays within 30% under fits verdict", () => {
    const r = computeAffordability({
      profile,
      targetPriceSgd: 600000,
      tenureYears: 25,
      cashOnHandSgd: 100000,
      cpfOaBalanceSgd: 200000,
      loanType: "hdb",
    });
    if (r.verdict === "fits") {
      expect(r.msrUtilization).toBeLessThanOrEqual(0.30);
    }
  });

  it("subtracts other monthly debt from TDSR sizing", () => {
    const r1 = computeAffordability({
      profile,
      targetPriceSgd: 600000,
      tenureYears: 25,
      cashOnHandSgd: 100000,
      cpfOaBalanceSgd: 200000,
    });
    const r2 = computeAffordability({
      profile,
      targetPriceSgd: 600000,
      tenureYears: 25,
      cashOnHandSgd: 100000,
      cpfOaBalanceSgd: 200000,
      otherMonthlyDebtSgd: 1500,
    });
    expect(r2.maxLoanByTdsrSgd).toBeLessThan(r1.maxLoanByTdsrSgd);
  });

  it("reports rules version stamp", () => {
    const r = computeAffordability({
      profile,
      targetPriceSgd: 600000,
      tenureYears: 25,
      cashOnHandSgd: 100000,
      cpfOaBalanceSgd: 200000,
    });
    expect(r.rulesVersion).toMatch(/\d+\.\d+/);
  });
});
