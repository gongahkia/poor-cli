import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  queryDatastore: vi.fn(),
}));

import { queryDatastore } from "../../datagov/client.js";
import { getHdbRentalPrices, getHdbResalePrices } from "../client.js";

describe("HDB client", () => {
  beforeEach(() => {
    vi.mocked(queryDatastore).mockReset();
  });

  it("normalizes curated resale rows", async () => {
    vi.mocked(queryDatastore).mockResolvedValue([
      {
        month: "2026-02",
        town: "BEDOK",
        flat_type: "4 ROOM",
        block: "101",
        street_name: "BEDOK NORTH AVE 4",
        storey_range: "10 TO 12",
        floor_area_sqm: "92",
        flat_model: "Model A",
        lease_commence_date: "1998",
        remaining_lease: "71 years 2 months",
        resale_price: "560000",
      },
    ]);

    const result = await getHdbResalePrices({
      town: "Bedok",
      startMonth: "2026-01",
      endMonth: "2026-03",
      limit: 20,
    });

    expect(result[0]).toMatchObject({
      town: "BEDOK",
      flatType: "4 ROOM",
      resalePrice: 560000,
      floorAreaSqm: 92,
    });
  });

  it("normalizes curated rental rows", async () => {
    vi.mocked(queryDatastore).mockResolvedValue([
      {
        rent_approval_date: "2026-02",
        town: "BEDOK",
        block: "101",
        street_name: "BEDOK NORTH AVE 4",
        flat_type: "4 ROOM",
        monthly_rent: "2900",
      },
    ]);

    const result = await getHdbRentalPrices({
      town: "Bedok",
      startMonth: "2026-01",
      endMonth: "2026-03",
      limit: 20,
    });

    expect(result[0]).toMatchObject({
      town: "BEDOK",
      flatType: "4 ROOM",
      monthlyRent: 2900,
    });
  });

  it("applies the month-range filter after datastore retrieval", async () => {
    vi.mocked(queryDatastore).mockResolvedValue([
      {
        month: "2025-12",
        town: "BEDOK",
        flat_type: "4 ROOM",
        block: "101",
        street_name: "BEDOK NORTH AVE 4",
        storey_range: "10 TO 12",
        floor_area_sqm: "92",
        flat_model: "Model A",
        lease_commence_date: "1998",
        remaining_lease: "71 years 2 months",
        resale_price: "560000",
      },
      {
        month: "2026-02",
        town: "BEDOK",
        flat_type: "4 ROOM",
        block: "101",
        street_name: "BEDOK NORTH AVE 4",
        storey_range: "10 TO 12",
        floor_area_sqm: "92",
        flat_model: "Model A",
        lease_commence_date: "1998",
        remaining_lease: "71 years 2 months",
        resale_price: "560000",
      },
    ]);

    const result = await getHdbResalePrices({
      town: "Bedok",
      startMonth: "2026-01",
      endMonth: "2026-03",
      limit: 20,
    });

    expect(result).toHaveLength(1);
    expect(result[0]?.month).toBe("2026-02");
  });

  it("keeps datastore fetches bounded when the requested limit is small", async () => {
    vi.mocked(queryDatastore).mockResolvedValue([
      {
        month: "2026-02",
        town: "BEDOK",
        flat_type: "4 ROOM",
        block: "101",
        street_name: "BEDOK NORTH AVE 4",
        storey_range: "10 TO 12",
        floor_area_sqm: "92",
        flat_model: "Model A",
        lease_commence_date: "1998",
        remaining_lease: "71 years 2 months",
        resale_price: "560000",
      },
    ]);

    await getHdbResalePrices({
      town: "Bedok",
      limit: 20,
    });

    expect(vi.mocked(queryDatastore)).toHaveBeenCalledWith(
      "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      expect.objectContaining({
        limit: 50,
      }),
    );
  });
});
