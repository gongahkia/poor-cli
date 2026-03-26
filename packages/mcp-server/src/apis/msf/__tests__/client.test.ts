import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  downloadDatasetGeoJson: vi.fn(),
}));

import { downloadDatasetGeoJson } from "../../datagov/client.js";
import { getMsfFamilyServices } from "../client.js";

const familyServicesFixture = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [103.83789640387423, 1.3688544443488972] },
      properties: {
        NAME: "Allkin Family Service Centre @ Ang Mo Kio 230",
        ADDRESSSTREETNAME: "Blk 230 Ang Mo Kio Ave 3 #01-1264",
        ADDRESSPOSTALCODE: "560230",
        ADDRESSBUILDINGNAME: null,
        ADDRESSBLOCKHOUSENUMBER: null,
        ADDRESSFLOORNUMBER: null,
        ADDRESSUNITNUMBER: null,
        DESCRIPTION: "Family Service Centres",
        TELEPHONE: "6453 5349",
        EMAIL: "fscamk@allkin.org.sg",
        HYPERLINK: "",
        FMEL_UPD_D: "20251203185226",
      },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [103.8462, 1.3698] },
      properties: {
        NAME: "Care Corner Family Service Centre",
        ADDRESSSTREETNAME: "",
        ADDRESSPOSTALCODE: "",
        ADDRESSBUILDINGNAME: "Care Corner Hub",
        ADDRESSBLOCKHOUSENUMBER: "85",
        ADDRESSFLOORNUMBER: "03",
        ADDRESSUNITNUMBER: "12",
        DESCRIPTION: "Family Service Centres",
        TELEPHONE: "61234567",
        EMAIL: "",
        HYPERLINK: "https://example.org/fsc",
        FMEL_UPD_D: "bad-timestamp",
      },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [] },
      properties: {
        NAME: "No Coordinates Family Service",
        ADDRESSSTREETNAME: "10 Example Street",
        ADDRESSPOSTALCODE: "123456",
        ADDRESSBUILDINGNAME: null,
        ADDRESSBLOCKHOUSENUMBER: null,
        ADDRESSFLOORNUMBER: null,
        ADDRESSUNITNUMBER: null,
        DESCRIPTION: null,
        TELEPHONE: null,
        EMAIL: null,
        HYPERLINK: null,
        FMEL_UPD_D: "20251203185226",
      },
    },
  ],
} as const;

describe("MSF civic directory client", () => {
  beforeEach(() => {
    vi.mocked(downloadDatasetGeoJson).mockReset();
    vi.mocked(downloadDatasetGeoJson).mockResolvedValue(familyServicesFixture as never);
  });

  it("normalizes family services and tolerates missing postal codes, malformed timestamps, and missing coordinates", async () => {
    const records = await getMsfFamilyServices({});

    expect(downloadDatasetGeoJson).toHaveBeenCalledWith("d_add23c06f7267e799185c79ccaa2099b", "STATIC");
    expect(records).toHaveLength(3);
    expect(records[0]).toMatchObject({
      name: "Allkin Family Service Centre @ Ang Mo Kio 230",
      category: "social_support",
      subcategory: "family_service_centre",
      address: "Blk 230 Ang Mo Kio Ave 3 #01-1264",
      postalCode: "560230",
      lastUpdatedAt: "2025-12-03T18:52:26+08:00",
      telephone: "6453 5349",
      email: "fscamk@allkin.org.sg",
      url: null,
    });
    expect(records[1]).toMatchObject({
      name: "Care Corner Family Service Centre",
      address: "85, #03-12, Care Corner Hub",
      postalCode: null,
      lastUpdatedAt: null,
      email: null,
      url: "https://example.org/fsc",
    });
    expect(records[2]).toMatchObject({
      name: "No Coordinates Family Service",
      lat: null,
      lng: null,
      postalCode: "123456",
    });
  });

  it("filters family services by name, postal code, and proximity", async () => {
    const records = await getMsfFamilyServices({
      name: "allkin",
      postalCode: "560230",
      lat: 1.3689,
      lng: 103.838,
      radiusKm: 0.2,
    });

    expect(records).toEqual([
      expect.objectContaining({
        name: "Allkin Family Service Centre @ Ang Mo Kio 230",
        postalCode: "560230",
      }),
    ]);
  });
});
