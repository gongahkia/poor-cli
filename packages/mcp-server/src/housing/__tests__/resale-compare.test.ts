import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/hdb/client.js", () => ({
  getHdbResalePrices: vi.fn(),
}));

import { getHdbResalePrices } from "../../apis/hdb/client.js";
import { compareResalePrice } from "../resale-compare.js";

const txn = (overrides: Partial<{ resalePrice: number; storeyRange: string; remainingLease: string }>) => ({
  month: "2026-02",
  town: "PUNGGOL",
  flatType: "4 ROOM",
  block: "100",
  streetName: "PUNGGOL FIELD",
  storeyRange: "10 TO 12",
  floorAreaSqm: 92,
  flatModel: "Model A",
  leaseCommenceDate: 2010,
  remainingLease: "84 years",
  resalePrice: 600000,
  ...overrides,
});

describe("compareResalePrice", () => {
  beforeEach(() => {
    vi.mocked(getHdbResalePrices).mockReset();
  });

  it("returns at_market verdict when asking is within 3% of median", async () => {
    vi.mocked(getHdbResalePrices).mockResolvedValue([
      txn({ resalePrice: 580000 }),
      txn({ resalePrice: 600000 }),
      txn({ resalePrice: 620000 }),
      txn({ resalePrice: 610000 }),
      txn({ resalePrice: 590000 }),
    ]);
    const r = await compareResalePrice({
      town: "PUNGGOL",
      flatType: "4 ROOM",
      askingPriceSgd: 605000,
    });
    expect(r.verdict).toBe("at_market");
    expect(r.stats.count).toBe(5);
    expect(r.variancePercent).not.toBeNull();
  });

  it("returns above_market when asking exceeds median by >3%", async () => {
    vi.mocked(getHdbResalePrices).mockResolvedValue([
      txn({ resalePrice: 580000 }),
      txn({ resalePrice: 600000 }),
      txn({ resalePrice: 620000 }),
    ]);
    const r = await compareResalePrice({
      town: "PUNGGOL",
      flatType: "4 ROOM",
      askingPriceSgd: 700000,
    });
    expect(r.verdict).toBe("above_market");
  });

  it("returns below_market when asking is below median by >3%", async () => {
    vi.mocked(getHdbResalePrices).mockResolvedValue([
      txn({ resalePrice: 580000 }),
      txn({ resalePrice: 600000 }),
      txn({ resalePrice: 620000 }),
    ]);
    const r = await compareResalePrice({
      town: "PUNGGOL",
      flatType: "4 ROOM",
      askingPriceSgd: 500000,
    });
    expect(r.verdict).toBe("below_market");
  });

  it("returns insufficient_data when fewer than 3 samples", async () => {
    vi.mocked(getHdbResalePrices).mockResolvedValue([txn({ resalePrice: 600000 })]);
    const r = await compareResalePrice({
      town: "PUNGGOL",
      flatType: "4 ROOM",
      askingPriceSgd: 605000,
    });
    expect(r.verdict).toBe("insufficient_data");
  });

  it("filters by storey band when provided", async () => {
    vi.mocked(getHdbResalePrices).mockResolvedValue([
      txn({ resalePrice: 600000, storeyRange: "10 TO 12" }),
      txn({ resalePrice: 650000, storeyRange: "13 TO 15" }),
      txn({ resalePrice: 605000, storeyRange: "10 TO 12" }),
      txn({ resalePrice: 595000, storeyRange: "10 TO 12" }),
    ]);
    const r = await compareResalePrice({
      town: "PUNGGOL",
      flatType: "4 ROOM",
      askingPriceSgd: 600000,
      storeyBand: "10 TO 12",
    });
    expect(r.stats.count).toBe(3);
  });

  it("filters by remaining-lease tolerance", async () => {
    vi.mocked(getHdbResalePrices).mockResolvedValue([
      txn({ resalePrice: 600000, remainingLease: "84 years" }),
      txn({ resalePrice: 700000, remainingLease: "70 years" }),
      txn({ resalePrice: 605000, remainingLease: "85 years" }),
      txn({ resalePrice: 595000, remainingLease: "82 years" }),
    ]);
    const r = await compareResalePrice({
      town: "PUNGGOL",
      flatType: "4 ROOM",
      askingPriceSgd: 600000,
      remainingLeaseYears: 84,
    });
    expect(r.stats.count).toBe(3);
  });

  it("computes percentile stats correctly", async () => {
    vi.mocked(getHdbResalePrices).mockResolvedValue(
      [500000, 550000, 600000, 650000, 700000].map((p) => txn({ resalePrice: p })),
    );
    const r = await compareResalePrice({
      town: "PUNGGOL",
      flatType: "4 ROOM",
      askingPriceSgd: 600000,
    });
    expect(r.stats.medianSgd).toBe(600000);
    expect(r.stats.minSgd).toBe(500000);
    expect(r.stats.maxSgd).toBe(700000);
  });
});
