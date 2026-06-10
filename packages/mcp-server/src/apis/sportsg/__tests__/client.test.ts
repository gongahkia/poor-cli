import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  downloadDatasetGeoJson: vi.fn(),
}));

import { downloadDatasetGeoJson } from "../../datagov/client.js";
import { getSportSgFacilities } from "../client.js";

describe("SportSG civic directory client", () => {
  beforeEach(() => {
    vi.mocked(downloadDatasetGeoJson).mockReset();
  });

  it("infers facility types and filters by type and proximity", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValueOnce({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [103.8513, 1.2842] },
          properties: {
            VENUE: "Downtown Swimming Complex",
            ADDRESSBLOCKHOUSENUMBER: "5",
            ADDRESSSTREETNAME: "Raffles Place",
            POSTAL_CODE: "048618",
            DETAILS: "https://www.activesgcircle.gov.sg/facilities",
            FMEL_UPD_D: "20240417181750",
          },
        },
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [103.8535, 1.2862] },
          properties: {
            VENUE: "Marina Sports Hall",
            ADDRESSBLOCKHOUSENUMBER: "1",
            ADDRESSSTREETNAME: "Fullerton Square",
            POSTAL_CODE: "049178",
            DETAILS: "https://www.activesgcircle.gov.sg/facilities",
            FMEL_UPD_D: "20240417181750",
          },
        },
      ],
    } as never);

    const results = await getSportSgFacilities({
      facilityType: "swimming_complex",
      lat: 1.28413,
      lng: 103.85146,
      radiusKm: 0.5,
    });

    expect(downloadDatasetGeoJson).toHaveBeenCalledWith("d_9b87bab59d036a60fad2a91530e10773", "STATIC");
    expect(results).toEqual([
      expect.objectContaining({
        name: "Downtown Swimming Complex",
        facilityType: "swimming_complex",
        postalCode: "048618",
        address: "5, Raffles Place",
        lastUpdatedAt: "2024-04-17T18:17:50+08:00",
      }),
    ]);
  });

  it("keeps malformed coordinates and postal codes nullable", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValueOnce({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [] },
          properties: {
            VENUE: "Broken Stadium",
            ADDRESSBLOCKHOUSENUMBER: "",
            ADDRESSSTREETNAME: "",
            POSTAL_CODE: "N/A",
            DETAILS: "",
            FMEL_UPD_D: "bad-timestamp",
          },
        },
      ],
    } as never);

    const results = await getSportSgFacilities({ name: "Broken" });

    expect(results).toEqual([
      expect.objectContaining({
        name: "Broken Stadium",
        facilityType: "stadium",
        postalCode: null,
        lat: null,
        lng: null,
        lastUpdatedAt: null,
      }),
    ]);
  });
});
