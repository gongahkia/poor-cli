import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  downloadDatasetCsvRows: vi.fn(),
}));

import { downloadDatasetCsvRows } from "../../datagov/client.js";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../client.js";

describe("HSA client", () => {
  beforeEach(() => {
    vi.mocked(downloadDatasetCsvRows).mockReset();
  });

  it("normalizes licensed pharmacy rows and extracts postal codes", async () => {
    vi.mocked(downloadDatasetCsvRows).mockResolvedValue([
      {
        pharmacy_name: "A.M. Pharmacy Pte Ltd",
        pharmacist_in_charge: "PARK YEON SANG",
        pharmacy_address: "150, ORCHARD ROAD, #04-06, ORCHARD PLAZA, SG(238841)",
      },
    ] as never);

    const result = await getHsaLicensedPharmacies({
      postalCode: "238841",
    });

    expect(downloadDatasetCsvRows).toHaveBeenCalledWith("d_bc50d72a9d61457964c6ea8d8ba7dce2", "DAILY");
    expect(result).toEqual([
      {
        pharmacyName: "A.M. Pharmacy Pte Ltd",
        pharmacistInCharge: "PARK YEON SANG",
        pharmacyAddress: "150, ORCHARD ROAD, #04-06, ORCHARD PLAZA, SG(238841)",
        postalCode: "238841",
      },
    ]);
  });

  it("normalizes health-product licensee rows and keeps exact company filtering", async () => {
    vi.mocked(downloadDatasetCsvRows).mockResolvedValue([
      {
        company_name: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
        license_type: "Controlled Drugs - Wholesale Licence",
        activity_type: "",
        dosage_form: "",
        expiry_date: "2025-07-20 00:00:00",
      },
      {
        company_name: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP HOLDINGS PTE. LTD.",
        license_type: "Controlled Drugs - Wholesale Licence",
        activity_type: "",
        dosage_form: "",
        expiry_date: "2025-07-20 00:00:00",
      },
    ] as never);

    const result = await getHsaHealthProductLicensees({
      companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
    });

    expect(downloadDatasetCsvRows).toHaveBeenCalledWith("d_bf50ce0f3f42f69d7acd50635afa62da", "DAILY");
    expect(result).toEqual([
      {
        companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
        licenseType: "Controlled Drugs - Wholesale Licence",
        activityType: null,
        dosageForm: null,
        expiryDate: "2025-07-20 00:00:00",
      },
    ]);
  });
});
