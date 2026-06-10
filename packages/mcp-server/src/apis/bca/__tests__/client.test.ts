import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  queryDatastoreExactMatches: vi.fn(),
}));

import { queryDatastoreExactMatches } from "../../datagov/client.js";
import { getBcaLicensedBuilders, getBcaRegisteredContractors } from "../client.js";

describe("BCA client", () => {
  beforeEach(() => {
    vi.mocked(queryDatastoreExactMatches).mockReset();
  });

  it("normalizes licensed-builder registry rows", async () => {
    vi.mocked(queryDatastoreExactMatches).mockResolvedValue([
      {
        company_name: "ABC CONSTRUCTION PTE LTD",
        uen_no: "201912345K",
        class: "General Builder Class 1",
        class_code: "GB1",
        additional_info: "",
        expiry_date: "2026-12-31",
        building_no: "1",
        street_name: "MAIN STREET",
        unit_no: "",
        building_name: "",
        postal_code: "123456",
        tel_no: "61234567",
      },
    ]);

    const result = await getBcaLicensedBuilders({
      companyName: "ABC CONSTRUCTION PTE LTD",
      limit: 10,
    });

    expect(result).toEqual([
      {
        companyName: "ABC CONSTRUCTION PTE LTD",
        uenNo: "201912345K",
        className: "General Builder Class 1",
        classCode: "GB1",
        additionalInfo: null,
        expiryDate: "2026-12-31",
        buildingNo: "1",
        streetName: "MAIN STREET",
        unitNo: null,
        buildingName: null,
        postalCode: "123456",
        telNo: "61234567",
      },
    ]);
  });

  it("normalizes registered-contractor registry rows and keeps exact filters", async () => {
    const exactRow = {
      company_name: "ABC CONSTRUCTION PTE LTD",
      uen_no: "201912345K",
      workhead: "CW01",
      grade: "C3",
      additional_info: "CRS",
      expiry_date: "2026-12-31",
      building_no: "",
      street_name: "MAIN STREET",
      unit_no: "",
      building_name: "",
      postal_code: "123456",
      tel_no: "61234567",
    };
    const broadRow = {
      company_name: "ABC CONSTRUCTION PTE LTD",
      uen_no: "201912345K",
      workhead: "CW01",
      grade: "A1",
      additional_info: "CRS",
      expiry_date: "2026-12-31",
      building_no: "",
      street_name: "MAIN STREET",
      unit_no: "",
      building_name: "",
      postal_code: "123456",
      tel_no: "61234567",
    };
    vi.mocked(queryDatastoreExactMatches).mockImplementation(async (_resourceId, options) => {
      expect(options?.exactMatch?.(exactRow)).toBe(true);
      expect(options?.exactMatch?.(broadRow)).toBe(false);
      return [exactRow];
    });

    const result = await getBcaRegisteredContractors({
      companyName: "abc construction pte ltd",
      uenNo: "201912345K",
      workhead: "CW01",
      grade: "C3",
      limit: 10,
    });

    expect(result).toEqual([
      expect.objectContaining({
      companyName: "ABC CONSTRUCTION PTE LTD",
      workhead: "CW01",
      grade: "C3",
      buildingNo: null,
      }),
    ]);
    expect(vi.mocked(queryDatastoreExactMatches)).toHaveBeenCalledWith(
      "d_dcda79be4aded5f9e769b8e23ff69b47",
      expect.objectContaining({
        matchLimit: 10,
        filters: {
          uen_no: "201912345K",
          workhead: { ilike: "CW01" },
          grade: { ilike: "C3" },
        },
      }),
    );
  });
});
