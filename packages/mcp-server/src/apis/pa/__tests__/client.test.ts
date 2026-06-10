import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  downloadDatasetGeoJson: vi.fn(),
}));

import { downloadDatasetGeoJson } from "../../datagov/client.js";
import { getPaCommunityOutlets, getPaResidentNetworkCentres } from "../client.js";

describe("PA civic directory client", () => {
  beforeEach(() => {
    vi.mocked(downloadDatasetGeoJson).mockReset();
  });

  it("normalizes community outlets and filters by type and proximity", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValueOnce({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [103.85105, 1.284] },
          properties: {
            NAME: "Downtown Community Club",
            DESCRIPTION: "CC",
            ADDRESSBLOCKHOUSENUMBER: "5",
            ADDRESSSTREETNAME: "Raffles Place",
            ADDRESSPOSTALCODE: "048616",
            HYPERLINK: "https://www.onepa.gov.sg/cc",
            FMEL_UPD_D: "20240417181750",
          },
        },
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [103.8537, 1.2864] },
          properties: {
            NAME: "PAssion WaVe Marina Bay",
            DESCRIPTION: "PW",
            ADDRESSBLOCKHOUSENUMBER: "1",
            ADDRESSSTREETNAME: "Fullerton Square",
            ADDRESSPOSTALCODE: "049178",
            HYPERLINK: "https://www.onepa.gov.sg/passion-wave",
            FMEL_UPD_D: "20240417181750",
          },
        },
      ],
    } as never);

    const results = await getPaCommunityOutlets({
      type: "community_club",
      lat: 1.28413,
      lng: 103.85146,
      radiusKm: 0.5,
    });

    expect(downloadDatasetGeoJson).toHaveBeenCalledWith("d_9de02d3fb33d96da1855f4fbef549a0f", "STATIC");
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({
      name: "Downtown Community Club",
      subcategory: "community_club",
      postalCode: "048616",
      address: "5, Raffles Place",
      sourceAgency: "People's Association",
      lastUpdatedAt: "2024-04-17T18:17:50+08:00",
      type: "community_club",
    });
    expect(results[0]?.distanceKm).toBeLessThan(0.5);
  });

  it("normalizes resident network centres and filters by postal code", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValueOnce({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [103.85146, 1.28413] },
          properties: {
            NAME: "Downtown Residents' Network Centre",
            ADDRESSBLOCKHOUSENUMBER: "1",
            ADDRESSSTREETNAME: "Raffles Place",
            ADDRESSPOSTALCODE: "048618",
            HYPERLINK: "https://www.onepa.gov.sg/rn",
            FMEL_UPD_D: "20240417181750",
          },
        },
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [] },
          properties: {
            NAME: "Broken Residents' Network Centre",
            ADDRESSBLOCKHOUSENUMBER: "",
            ADDRESSSTREETNAME: "",
            ADDRESSPOSTALCODE: "",
            HYPERLINK: "",
            FMEL_UPD_D: "bad-timestamp",
          },
        },
      ],
    } as never);

    const results = await getPaResidentNetworkCentres({
      postalCode: "048618",
    });

    expect(downloadDatasetGeoJson).toHaveBeenCalledWith("d_9ae25d6b3fefdd15983c4e46ecc7fcbd", "STATIC");
    expect(results).toEqual([
      expect.objectContaining({
        name: "Downtown Residents' Network Centre",
        subcategory: "resident_network_centre",
        postalCode: "048618",
        lat: 1.28413,
        lng: 103.85146,
      }),
    ]);
  });
});
