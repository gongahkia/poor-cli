import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("@sg-apis/shared", async () => {
  const actual = await vi.importActual<typeof import("@sg-apis/shared")>("@sg-apis/shared");
  return {
    ...actual,
    getRateLimiter: () => ({ acquire: vi.fn().mockResolvedValue(undefined) }),
    Keystore: class {
      getKey(name: string) { return name === "ura" ? "test-key" : null; }
      close() {}
    },
  };
});

vi.mock("../../../middleware/cache-middleware.js", () => ({
  withCache: vi.fn(async (_key: string, _ttl: number, fetcher: () => Promise<unknown>) => ({
    data: await fetcher(),
    cached: false,
  })),
  buildCacheKey: vi.fn((...args: unknown[]) => args.join(":")),
}));

import { normalizeTransactions } from "../normalizer.js";

describe("URA client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("normalizes transaction data", () => {
    const raw = [
      { project: "THE SAIL", street: "MARINA BLVD", x: "30219.45", y: "29321.78", marketSegment: "CCR", area: "51-75", floorRange: "26-30", noOfUnits: "1", contractDate: "0125", typeOfSale: "2", price: "1280000", propertyType: "Condominium", district: "01", typeOfArea: "Strata", tenure: "99 yrs", nettPrice: "-" },
    ];
    const normalized = normalizeTransactions(raw);
    expect(normalized).toHaveLength(1);
    expect(normalized[0]?.price).toBe(1280000);
    expect(typeof normalized[0]?.price).toBe("number");
  });

  it("normalizes contract date from MMYY to YYYY-MM", () => {
    const raw = [
      { project: "TEST", street: "TEST ST", x: "0", y: "0", marketSegment: "OCR", area: "50", floorRange: "01-05", noOfUnits: "1", contractDate: "0324", typeOfSale: "3", price: "500000", propertyType: "Apartment", district: "15", typeOfArea: "Strata", tenure: "Freehold", nettPrice: "-" },
    ];
    const normalized = normalizeTransactions(raw);
    expect(normalized[0]?.contractDate).toBe("2024-03");
  });

  it("maps sale type codes to labels", () => {
    const raw = [
      { project: "TEST", street: "TEST", x: "0", y: "0", marketSegment: "RCR", area: "76-100", floorRange: "06-10", noOfUnits: "1", contractDate: "0125", typeOfSale: "1", price: "1000000", propertyType: "Condominium", district: "10", typeOfArea: "Strata", tenure: "99 yrs", nettPrice: "-" },
    ];
    const normalized = normalizeTransactions(raw);
    expect(normalized[0]?.saleType).toBe("New Sale");
  });

  it("parses coordinates from strings", () => {
    const raw = [
      { project: "TEST", street: "TEST", x: "30219.45", y: "29321.78", marketSegment: "CCR", area: "51-75", floorRange: "26-30", noOfUnits: "2", contractDate: "0125", typeOfSale: "2", price: "2000000", propertyType: "Condominium", district: "01", typeOfArea: "Strata", tenure: "99 yrs", nettPrice: "-" },
    ];
    const normalized = normalizeTransactions(raw);
    expect(typeof normalized[0]?.lat).toBe("number");
    expect(typeof normalized[0]?.lng).toBe("number");
  });

  it("handles multiple units", () => {
    const raw = [
      { project: "TEST", street: "TEST", x: "0", y: "0", marketSegment: "OCR", area: "100", floorRange: "01-05", noOfUnits: "5", contractDate: "0125", typeOfSale: "1", price: "5000000", propertyType: "Apartment", district: "20", typeOfArea: "Strata", tenure: "99 yrs", nettPrice: "-" },
    ];
    const normalized = normalizeTransactions(raw);
    expect(normalized[0]?.units).toBe(5);
  });
});
