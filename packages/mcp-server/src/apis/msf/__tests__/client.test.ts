import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  downloadDatasetGeoJson: vi.fn(),
}));

import { downloadDatasetGeoJson } from "../../datagov/client.js";
import {
  getMsfFamilyServices,
  getMsfSocialServiceOffices,
  getMsfStudentCareServices,
} from "../client.js";

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

const studentCareFixture = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [103.81584893819745, 1.4520108099275582] },
      properties: {
        NAME_OF_STUDENT_CARE_CENTRE: "YMCA Student Care Centre @ Canberra",
        SCC_ADDRESS: "471, Sembawang Drive, #1 421, Singapore 750471",
        SCC_POSTAL_CODE: "750471",
        SCC_TELEPHONE: "98375096",
        SCC_EMAIL: "cbscc@ymca.edu.sg",
        AUDIT_STATUS: "Grade A",
        AUDIT_DATE: "20260123",
        SCFA_Y_N: "Y",
        BUSINESS_PROFILE: "Commercial Companies",
        MONTHLY_FEE: "$295",
        ENROLMENT: 100,
        FMEL_UPD_D: "20260223124833",
      },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [103.8189, 1.4471] },
      properties: {
        NAME_OF_STUDENT_CARE_CENTRE: "Sparkle Student Care",
        SCC_ADDRESS: "300 Canberra Road",
        SCC_POSTAL_CODE: "",
        SCC_TELEPHONE: "",
        SCC_EMAIL: "",
        AUDIT_STATUS: "Grade B",
        AUDIT_DATE: "bad-date",
        SCFA_Y_N: "N",
        BUSINESS_PROFILE: "Voluntary Welfare Organisation",
        MONTHLY_FEE: "$420",
        ENROLMENT: "85",
        FMEL_UPD_D: "bad-timestamp",
      },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [] },
      properties: {
        NAME_OF_STUDENT_CARE_CENTRE: "No Coordinates Student Care",
        SCC_ADDRESS: "10 Example Street",
        SCC_POSTAL_CODE: "123456",
        SCC_TELEPHONE: null,
        SCC_EMAIL: null,
        AUDIT_STATUS: null,
        AUDIT_DATE: null,
        SCFA_Y_N: null,
        BUSINESS_PROFILE: null,
        MONTHLY_FEE: null,
        ENROLMENT: null,
        FMEL_UPD_D: "20260223124833",
      },
    },
  ],
} as const;

const socialServiceOfficesFixture = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [103.80620757407047, 1.2964584179145409] },
      properties: {
        NAME: "Social Service Office @ Queenstown",
        BLOCKHOUSENUMBER: "40",
        STREETNAME: "Margaret Drive",
        FLOORNUMBER: "#02-",
        UNITNUMBER: "01",
        BUILDINGNAME: null,
        POSTALCODE: "140040",
        HYPERLINK: "",
        DESCRIPTION: "Social Service Offices",
        FMEL_UPD_D: "20241104113604",
      },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [103.8212, 1.305] },
      properties: {
        NAME: "Social Service Office @ Bukit Merah",
        BLOCKHOUSENUMBER: "",
        STREETNAME: "",
        FLOORNUMBER: "",
        UNITNUMBER: "",
        BUILDINGNAME: "Bukit Merah Family Hub",
        POSTALCODE: "",
        HYPERLINK: "https://example.org/sso",
        DESCRIPTION: "Social Service Offices",
        FMEL_UPD_D: "bad-timestamp",
      },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [] },
      properties: {
        NAME: "No Coordinates Social Service Office",
        BLOCKHOUSENUMBER: "10",
        STREETNAME: "Example Street",
        FLOORNUMBER: null,
        UNITNUMBER: null,
        BUILDINGNAME: null,
        POSTALCODE: "123456",
        HYPERLINK: null,
        DESCRIPTION: null,
        FMEL_UPD_D: "20241104113604",
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

  it("normalizes student care services and supports audit-status, SCFA, postal-code, and proximity filters", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValueOnce(studentCareFixture as never);

    const records = await getMsfStudentCareServices({
      auditStatus: "grade a",
      scfaOnly: true,
      postalCode: "750471",
      lat: 1.452,
      lng: 103.816,
      radiusKm: 0.5,
    });

    expect(records).toEqual([
      expect.objectContaining({
        name: "YMCA Student Care Centre @ Canberra",
        category: "childcare",
        subcategory: "student_care",
        postalCode: "750471",
        auditStatus: "Grade A",
        auditDate: "2026-01-23",
        scfa: true,
        monthlyFee: 295,
        enrolment: 100,
      }),
    ]);
  });

  it("normalizes malformed student care rows without throwing", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValueOnce(studentCareFixture as never);

    const records = await getMsfStudentCareServices({});

    const malformedRecord = records.find((record) => record.name === "Sparkle Student Care");
    expect(malformedRecord).toMatchObject({
      name: "Sparkle Student Care",
      postalCode: null,
      auditDate: "bad-date",
      scfa: false,
      monthlyFee: 420,
      enrolment: 85,
      telephone: null,
      email: null,
      lastUpdatedAt: null,
    });
    const noCoordsRecord = records.find((record) => record.name === "No Coordinates Student Care");
    expect(noCoordsRecord).toMatchObject({
      name: "No Coordinates Student Care",
      lat: null,
      lng: null,
      postalCode: "123456",
    });
  });

  it("normalizes social service offices and fixes fragmented floor-unit addresses", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValueOnce(socialServiceOfficesFixture as never);

    const records = await getMsfSocialServiceOffices({});

    const queenstown = records.find((record) => record.name === "Social Service Office @ Queenstown");
    expect(queenstown).toMatchObject({
      name: "Social Service Office @ Queenstown",
      address: "40, Margaret Drive, #02-01",
      postalCode: "140040",
      description: "Social Service Offices",
      url: null,
      lastUpdatedAt: "2024-11-04T11:36:04+08:00",
    });
    const bukitMerah = records.find((record) => record.name === "Social Service Office @ Bukit Merah");
    expect(bukitMerah).toMatchObject({
      name: "Social Service Office @ Bukit Merah",
      address: "Bukit Merah Family Hub",
      postalCode: null,
      url: "https://example.org/sso",
      lastUpdatedAt: null,
    });
    const noCoordsRecord = records.find((record) => record.name === "No Coordinates Social Service Office");
    expect(noCoordsRecord).toMatchObject({
      name: "No Coordinates Social Service Office",
      lat: null,
      lng: null,
      postalCode: "123456",
    });
  });

  it("filters social service offices by name, postal code, and proximity", async () => {
    vi.mocked(downloadDatasetGeoJson).mockResolvedValueOnce(socialServiceOfficesFixture as never);

    const records = await getMsfSocialServiceOffices({
      name: "queenstown",
      postalCode: "140040",
      lat: 1.29645,
      lng: 103.8062,
      radiusKm: 0.2,
    });

    expect(records).toEqual([
      expect.objectContaining({
        name: "Social Service Office @ Queenstown",
        postalCode: "140040",
      }),
    ]);
  });
});
