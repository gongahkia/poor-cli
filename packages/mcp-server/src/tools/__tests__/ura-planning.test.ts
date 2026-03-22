import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/onemap/client.js", () => ({
  geocode: vi.fn(),
}));

vi.mock("../../apis/ura/client.js", () => ({
  getPropertyTransactions: vi.fn(),
  uraFetch: vi.fn(),
}));

import { geocode } from "../../apis/onemap/client.js";
import { uraFetch } from "../../apis/ura/client.js";
import { lookupPlanningArea } from "../ura-tools.js";

describe("lookupPlanningArea", () => {
  beforeEach(() => {
    vi.mocked(geocode).mockReset();
    vi.mocked(uraFetch).mockReset();
  });

  it("uses direct coordinates when provided", async () => {
    vi.mocked(uraFetch).mockResolvedValue({
      Status: "OK",
      Result: [{ pln_area_n: "TAMPINES", region: "East Region" }],
    });

    const result = await lookupPlanningArea({ lat: 1.3521, lng: 103.945 });

    expect(uraFetch).toHaveBeenCalledWith("GET_PLANNING_AREA", {
      lat: "1.3521",
      lng: "103.945",
    });
    expect(result).toEqual([{ planningArea: "TAMPINES", region: "East Region" }]);
  });

  it("geocodes planning area names before URA lookup", async () => {
    vi.mocked(geocode).mockResolvedValue([
      {
        address: "Tampines Ave 1",
        building: "TEST",
        postal: "520000",
        lat: 1.3521,
        lng: 103.945,
        x: 0,
        y: 0,
      },
    ]);
    vi.mocked(uraFetch).mockResolvedValue({
      Status: "OK",
      Result: [{ pln_area_n: "TAMPINES", region: "East Region" }],
    });

    const result = await lookupPlanningArea({ planningArea: "Tampines" });

    expect(geocode).toHaveBeenCalledWith("Tampines", 1);
    expect(uraFetch).toHaveBeenCalledWith("GET_PLANNING_AREA", {
      lat: "1.3521",
      lng: "103.945",
    });
    expect(result).toEqual([{ planningArea: "TAMPINES", region: "East Region" }]);
  });

  it("throws when the planning area cannot be resolved", async () => {
    vi.mocked(geocode).mockResolvedValue([]);

    await expect(lookupPlanningArea({ planningArea: "Unknown Place" })).rejects.toThrow(
      "Could not resolve planning area: Unknown Place",
    );
  });
});
