import { describe, expect, it } from "vitest";
import { computeGrantEligibility } from "../grants.js";
import type { HouseholdProfile } from "../grants.js";

const couple = (overrides?: Partial<HouseholdProfile>): HouseholdProfile => ({
  applicants: [
    { age: 30, citizenship: "citizen", monthlyIncomeSgd: 4000, employmentMonths: 24, firstTimer: true },
    { age: 29, citizenship: "citizen", monthlyIncomeSgd: 4000, employmentMonths: 24, firstTimer: true },
  ],
  maritalStatus: "married",
  flatMode: "resale",
  flatSize: "4_room",
  proximityToParents: "neither",
  ...overrides,
});

describe("computeGrantEligibility — EHG", () => {
  it("awards EHG for citizen first-timer couple within ceiling", () => {
    const r = computeGrantEligibility(couple());
    const ehg = r.eligible.find((g) => g.id === "ehg");
    expect(ehg).toBeDefined();
    expect(ehg!.amountSgd).toBe(20000); // income 8000 -> tier <=8000 = 20k (Aug 2024 update)
  });

  it("awards higher EHG tier for lower income", () => {
    const r = computeGrantEligibility(couple({
      applicants: [
        { age: 30, citizenship: "citizen", monthlyIncomeSgd: 1500, employmentMonths: 24, firstTimer: true },
        { age: 29, citizenship: "citizen", monthlyIncomeSgd: 1500, employmentMonths: 24, firstTimer: true },
      ],
    }));
    expect(r.eligible.find((g) => g.id === "ehg")?.amountSgd).toBe(95000); // income 3000 -> tier <=3000 = 95k (Aug 2024 update)
  });

  it("blocks EHG when income exceeds ceiling", () => {
    const r = computeGrantEligibility(couple({
      applicants: [
        { age: 30, citizenship: "citizen", monthlyIncomeSgd: 5000, employmentMonths: 24, firstTimer: true },
        { age: 29, citizenship: "citizen", monthlyIncomeSgd: 5000, employmentMonths: 24, firstTimer: true },
      ],
    }));
    expect(r.eligible.find((g) => g.id === "ehg")).toBeUndefined();
    expect(r.ineligible.find((b) => b.grantId === "ehg" && b.code === "INCOME_OVER_CEILING")).toBeDefined();
  });

  it("blocks EHG for non-first-timer", () => {
    const r = computeGrantEligibility(couple({
      applicants: [
        { age: 30, citizenship: "citizen", monthlyIncomeSgd: 4000, employmentMonths: 24, firstTimer: false },
        { age: 29, citizenship: "citizen", monthlyIncomeSgd: 4000, employmentMonths: 24, firstTimer: true },
      ],
    }));
    expect(r.ineligible.find((b) => b.grantId === "ehg" && b.code === "NOT_FIRST_TIMER")).toBeDefined();
  });

  it("blocks EHG when employment under 12 months", () => {
    const r = computeGrantEligibility(couple({
      applicants: [
        { age: 30, citizenship: "citizen", monthlyIncomeSgd: 4000, employmentMonths: 6, firstTimer: true },
        { age: 29, citizenship: "citizen", monthlyIncomeSgd: 4000, employmentMonths: 24, firstTimer: true },
      ],
    }));
    expect(r.ineligible.find((b) => b.grantId === "ehg" && b.code === "EMPLOYMENT_INSUFFICIENT")).toBeDefined();
  });

  it("halves EHG amount for single applicant and uses singles ceiling", () => {
    const r = computeGrantEligibility({
      applicants: [
        { age: 36, citizenship: "citizen", monthlyIncomeSgd: 3000, employmentMonths: 24, firstTimer: true },
      ],
      maritalStatus: "single",
      flatMode: "resale",
      flatSize: "3_room",
    });
    const ehg = r.eligible.find((g) => g.id === "ehg");
    expect(ehg).toBeDefined();
    expect(ehg!.amountSgd).toBeGreaterThan(0);
    expect(ehg!.basis).toContain("Singles");
  });

  it("blocks EHG for single applicant over halved ceiling", () => {
    const r = computeGrantEligibility({
      applicants: [
        { age: 36, citizenship: "citizen", monthlyIncomeSgd: 5000, employmentMonths: 24, firstTimer: true },
      ],
      maritalStatus: "single",
      flatMode: "resale",
      flatSize: "3_room",
    });
    expect(r.ineligible.find((b) => b.grantId === "ehg" && b.code === "INCOME_OVER_CEILING")).toBeDefined();
  });
});

describe("computeGrantEligibility — Family Grant", () => {
  it("awards family grant SC/SC 2-4 room resale", () => {
    const r = computeGrantEligibility(couple({ flatSize: "4_room" }));
    const fam = r.eligible.find((g) => g.id === "family_grant");
    expect(fam?.amountSgd).toBe(80000);
  });

  it("awards reduced family grant for 5-room+", () => {
    const r = computeGrantEligibility(couple({ flatSize: "5_room" }));
    const fam = r.eligible.find((g) => g.id === "family_grant");
    expect(fam?.amountSgd).toBe(50000);
  });

  it("awards SC/PR family grant", () => {
    const r = computeGrantEligibility(couple({
      applicants: [
        { age: 30, citizenship: "citizen", monthlyIncomeSgd: 4000, employmentMonths: 24, firstTimer: true },
        { age: 29, citizenship: "pr", monthlyIncomeSgd: 4000, employmentMonths: 24, firstTimer: true },
      ],
      flatSize: "4_room",
    }));
    expect(r.eligible.find((g) => g.id === "family_grant")?.amountSgd).toBe(70000);
  });

  it("does not apply family grant for BTO", () => {
    const r = computeGrantEligibility(couple({ flatMode: "bto" }));
    expect(r.eligible.find((g) => g.id === "family_grant")).toBeUndefined();
  });
});

describe("computeGrantEligibility — Singles Grant", () => {
  it("awards singles grant for citizen 35+ first-timer 4-room resale", () => {
    const r = computeGrantEligibility({
      applicants: [{ age: 36, citizenship: "citizen", monthlyIncomeSgd: 5000, employmentMonths: 24, firstTimer: true }],
      maritalStatus: "single",
      flatMode: "resale",
      flatSize: "4_room",
    });
    expect(r.eligible.find((g) => g.id === "singles_grant")?.amountSgd).toBe(40000);
  });

  it("blocks singles grant for under-35", () => {
    const r = computeGrantEligibility({
      applicants: [{ age: 32, citizenship: "citizen", monthlyIncomeSgd: 5000, employmentMonths: 24, firstTimer: true }],
      maritalStatus: "single",
      flatMode: "resale",
      flatSize: "4_room",
    });
    expect(r.ineligible.find((b) => b.grantId === "singles_grant" && b.code === "AGE_BELOW_35")).toBeDefined();
  });

  it("doubles singles grant when joint singles", () => {
    const r = computeGrantEligibility({
      applicants: [
        { age: 36, citizenship: "citizen", monthlyIncomeSgd: 3000, employmentMonths: 24, firstTimer: true },
        { age: 36, citizenship: "citizen", monthlyIncomeSgd: 3000, employmentMonths: 24, firstTimer: true },
      ],
      maritalStatus: "joint_singles",
      flatMode: "resale",
      flatSize: "4_room",
    });
    expect(r.eligible.find((g) => g.id === "singles_grant")?.amountSgd).toBe(50000); // joint singles 4-room (verified 2026-04-29)
  });
});

describe("computeGrantEligibility — Proximity Grant", () => {
  it("awards 30k for family living with parents", () => {
    const r = computeGrantEligibility(couple({ proximityToParents: "live_with" }));
    expect(r.eligible.find((g) => g.id === "proximity_grant")?.amountSgd).toBe(30000);
  });

  it("awards 20k for family near parents", () => {
    const r = computeGrantEligibility(couple({ proximityToParents: "near" }));
    expect(r.eligible.find((g) => g.id === "proximity_grant")?.amountSgd).toBe(20000);
  });

  it("does not award proximity for BTO", () => {
    const r = computeGrantEligibility(couple({ flatMode: "bto", proximityToParents: "live_with" }));
    expect(r.eligible.find((g) => g.id === "proximity_grant")).toBeUndefined();
  });

  it("does not award proximity when neither", () => {
    const r = computeGrantEligibility(couple({ proximityToParents: "neither" }));
    expect(r.eligible.find((g) => g.id === "proximity_grant")).toBeUndefined();
  });
});

describe("computeGrantEligibility — totals + provenance", () => {
  it("sums multiple grants and stamps rules version", () => {
    const r = computeGrantEligibility(couple({ proximityToParents: "near" }));
    const sum = r.eligible.reduce((acc, g) => acc + g.amountSgd, 0);
    expect(r.totalSgd).toBe(sum);
    expect(r.rulesVersion).toMatch(/\d+\.\d+/);
    expect(r.rulesLastVerified).toMatch(/\d{4}-\d{2}-\d{2}/);
    expect(r.assumptions.length).toBeGreaterThan(0);
  });

  it("returns empty eligible[] for foreigner-only household", () => {
    const r = computeGrantEligibility({
      applicants: [{ age: 35, citizenship: "foreigner", monthlyIncomeSgd: 5000, employmentMonths: 24 }],
      maritalStatus: "single",
      flatMode: "resale",
      flatSize: "4_room",
    });
    expect(r.eligible).toHaveLength(0);
    expect(r.totalSgd).toBe(0);
  });
});
