import { describe, expect, it } from "vitest";
import { compareLoans } from "../loans.js";

describe("compareLoans", () => {
  it("includes HDB concessionary quote by default", () => {
    const r = compareLoans({
      priceSgd: 600000,
      downpaymentSgd: 150000,
      tenureYears: 25,
    });
    const hdb = r.quotes.find((q) => q.source === "HDB");
    expect(hdb).toBeDefined();
    expect(hdb!.principalSgd).toBe(450000);
    expect(hdb!.effectiveYear1Rate).toBeGreaterThan(0);
    expect(hdb!.monthlyInstalmentYear1Sgd).toBeGreaterThan(0);
  });

  it("excludes HDB quote when includeHdbLoan false", () => {
    const r = compareLoans({
      priceSgd: 600000,
      downpaymentSgd: 150000,
      tenureYears: 25,
      includeHdbLoan: false,
    });
    expect(r.quotes.find((q) => q.source === "HDB")).toBeUndefined();
  });

  it("caps HDB quote tenure at 25y", () => {
    const r = compareLoans({
      priceSgd: 600000,
      downpaymentSgd: 150000,
      tenureYears: 30,
    });
    const hdb = r.quotes.find((q) => q.source === "HDB");
    expect(hdb!.tenureYears).toBe(25);
  });

  it("prices SORA-pegged bank package given live SORA", () => {
    const r = compareLoans({
      priceSgd: 600000,
      downpaymentSgd: 150000,
      tenureYears: 25,
      soraValue: 0.031,
      bankPackages: [
        { bank: "DBS", packageName: "3M SORA + 0.85%", rateBasis: "sora_3m", spreadBps: 85, lockInYears: 2 },
      ],
      includeHdbLoan: false,
    });
    expect(r.quotes).toHaveLength(1);
    expect(r.quotes[0]!.effectiveYear1Rate).toBeCloseTo(0.0395, 3);
    expect(r.quotes[0]!.monthlyInstalmentYear1Sgd).toBeGreaterThan(0);
  });

  it("flags SORA package with no SORA value supplied", () => {
    const r = compareLoans({
      priceSgd: 600000,
      downpaymentSgd: 150000,
      tenureYears: 25,
      bankPackages: [
        { bank: "OCBC", packageName: "1M SORA + 0.80%", rateBasis: "sora_1m", spreadBps: 80 },
      ],
      includeHdbLoan: false,
    });
    expect(r.quotes[0]!.monthlyInstalmentYear1Sgd).toBe(0);
    expect(r.quotes[0]!.notes.join(" ")).toMatch(/SORA value missing/i);
  });

  it("prices fixed-rate package without SORA", () => {
    const r = compareLoans({
      priceSgd: 600000,
      downpaymentSgd: 150000,
      tenureYears: 25,
      bankPackages: [
        { bank: "UOB", packageName: "Fixed 3.2% 2y", rateBasis: "fixed", fixedRate: 0.032, lockInYears: 2 },
      ],
      includeHdbLoan: false,
    });
    expect(r.quotes[0]!.effectiveYear1Rate).toBeCloseTo(0.032, 4);
  });

  it("identifies bestByYear1 and bestByLifetime", () => {
    const r = compareLoans({
      priceSgd: 600000,
      downpaymentSgd: 150000,
      tenureYears: 25,
      soraValue: 0.031,
      bankPackages: [
        { bank: "DBS", packageName: "3M SORA + 0.85%", rateBasis: "sora_3m", spreadBps: 85, lockInYears: 2 },
        { bank: "OCBC", packageName: "1M SORA + 0.80%", rateBasis: "sora_1m", spreadBps: 80, lockInYears: 2 },
      ],
    });
    expect(r.bestByYear1).not.toBeNull();
    expect(r.bestByLifetime).not.toBeNull();
  });

  it("returns no bests when no quotes priced", () => {
    const r = compareLoans({
      priceSgd: 600000,
      downpaymentSgd: 150000,
      tenureYears: 25,
      includeHdbLoan: false,
    });
    expect(r.bestByYear1).toBeNull();
    expect(r.bestByLifetime).toBeNull();
  });

  it("reports stress-test rate from rules", () => {
    const r = compareLoans({ priceSgd: 600000, downpaymentSgd: 150000, tenureYears: 25 });
    expect(r.stressRate).toBe(0.04);
  });
});
