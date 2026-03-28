import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  downloadDatasetGeoJson: vi.fn(),
}));

import { downloadDatasetGeoJson } from "../../datagov/client.js";
import { getHlbHotels } from "../client.js";

describe("HLB client", () => {
  beforeEach(() => {
    vi.mocked(downloadDatasetGeoJson).mockReset();
  });

  it("normalizes hotel GeoJSON features", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValue({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [103.851, 1.284] },
          properties: {
            NAME: "RAFFLES HOTEL SINGAPORE",
            DESCRIPTION: "1 BEACH ROAD",
            POSTALCODE: "189673",
            KEEPERNAME: "RAFFLES HOTEL SINGAPORE",
            TOTALROOMS: "115",
            HYPERLINK: "https://example.com",
            INC_CRC: "Y",
            FMEL_UPD_D: "20240417181750",
          },
        },
      ],
    } as never);

    const result = await getHlbHotels({
      keeperName: "raffles hotel singapore",
    });

    expect(downloadDatasetGeoJson).toHaveBeenCalledWith("d_654e22f14e5bb817423f0e0c9ac4f632", "DAILY");
    expect(result).toEqual([
      expect.objectContaining({
        name: "RAFFLES HOTEL SINGAPORE",
        address: "1 BEACH ROAD",
        postalCode: "189673",
        keeperName: "RAFFLES HOTEL SINGAPORE",
        totalRooms: 115,
        url: "https://example.com",
        incCrc: "Y",
        lastUpdatedAt: "2024-04-17T18:17:50+08:00",
      }),
    ]);
  });

  it("supports name and postal filters via directory helpers", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValue({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [103.851, 1.284] },
          properties: {
            NAME: "HOTEL ONE",
            DESCRIPTION: "1 BEACH ROAD",
            POSTALCODE: "189673",
            KEEPERNAME: "OPERATOR ONE",
            TOTALROOMS: "100",
          },
        },
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [103.852, 1.285] },
          properties: {
            NAME: "HOTEL TWO",
            DESCRIPTION: "2 BEACH ROAD",
            POSTALCODE: "189674",
            KEEPERNAME: "OPERATOR TWO",
            TOTALROOMS: "120",
          },
        },
      ],
    } as never);

    const result = await getHlbHotels({
      name: "hotel two",
      postalCode: "189674",
    });

    expect(result).toEqual([
      expect.objectContaining({
        name: "HOTEL TWO",
        postalCode: "189674",
      }),
    ]);
  });
});
