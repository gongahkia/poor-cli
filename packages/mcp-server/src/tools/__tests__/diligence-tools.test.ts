import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/cea/client.js", () => ({
  getCeaSalespersons: vi.fn(),
}));

vi.mock("../../apis/bca/client.js", () => ({
  getBcaLicensedBuilders: vi.fn(),
  getBcaRegisteredContractors: vi.fn(),
}));

vi.mock("../../apis/acra/client.js", () => ({
  getAcraEntities: vi.fn(),
}));

import { getAcraEntities } from "../../apis/acra/client.js";
import { getCeaSalespersons } from "../../apis/cea/client.js";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../../apis/bca/client.js";
import { handleAcraEntities } from "../acra-tools.js";
import {
  handleBcaLicensedBuilders,
  handleBcaRegisteredContractors,
} from "../bca-tools.js";
import { handleCeaSalespersons } from "../cea-tools.js";

describe("diligence tool handlers", () => {
  beforeEach(() => {
    vi.mocked(getAcraEntities).mockReset();
    vi.mocked(getCeaSalespersons).mockReset();
    vi.mocked(getBcaLicensedBuilders).mockReset();
    vi.mocked(getBcaRegisteredContractors).mockReset();
  });

  it("formats ACRA entity results with structured content", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        uen: "201912345K",
        issuanceAgencyId: "ACRA",
        entityName: "ABC CONSTRUCTION PTE LTD",
        entityTypeDescription: "Local Company",
        businessConstitutionDescription: null,
        companyTypeDescription: "Private Company Limited by Shares",
        pafConstitutionDescription: null,
        entityStatusDescription: "Live Company",
        registrationIncorporationDate: "2019-04-01",
        uenIssueDate: "2019-04-01",
        addressType: "LOCAL",
        block: "1",
        streetName: "MAIN STREET",
        levelNo: "02",
        unitNo: "01",
        buildingName: "ABC BUILDING",
        postalCode: "123456",
        otherAddressLine1: null,
        otherAddressLine2: null,
        accountDueDate: "2026-04-01",
        annualReturnDate: "2025-04-01",
        primarySsicCode: "41001",
        primarySsicDescription: "GENERAL CONTRACTORS",
        primaryUserDescribedActivity: null,
        secondarySsicCode: null,
        secondarySsicDescription: null,
        secondaryUserDescribedActivity: null,
        noOfOfficers: 3,
      },
    ]);

    const result = await handleAcraEntities({
      entityName: "ABC CONSTRUCTION PTE LTD",
      format: "json",
    });

    expect(result.structuredContent).toMatchObject({
      records: [
        expect.objectContaining({
          entityName: "ABC CONSTRUCTION PTE LTD",
          uen: "201912345K",
        }),
      ],
    });
  });

  it("formats CEA salesperson results with structured content", async () => {
    vi.mocked(getCeaSalespersons).mockResolvedValue([
      {
        salespersonName: "JANE TAN",
        registrationNo: "R123456A",
        registrationStartDate: "2011-01-01",
        registrationEndDate: "2026-12-31",
        estateAgentName: "ERA REALTY NETWORK PTE LTD",
        estateAgentLicenseNo: "L3002382K",
      },
    ]);

    const result = await handleCeaSalespersons({
      salespersonName: "JANE TAN",
      format: "json",
    });

    expect(result.structuredContent).toMatchObject({
      records: [
        expect.objectContaining({
          salespersonName: "JANE TAN",
        }),
      ],
    });
  });

  it("formats BCA licensed-builder results with structured content", async () => {
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([
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

    const result = await handleBcaLicensedBuilders({
      companyName: "ABC CONSTRUCTION PTE LTD",
      format: "json",
    });

    expect(result.structuredContent).toMatchObject({
      records: [
        expect.objectContaining({
          companyName: "ABC CONSTRUCTION PTE LTD",
        }),
      ],
    });
  });

  it("formats BCA registered-contractor results with structured content", async () => {
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([
      {
        companyName: "ABC CONSTRUCTION PTE LTD",
        uenNo: "201912345K",
        workhead: "CW01",
        grade: "C3",
        additionalInfo: "CRS",
        expiryDate: "2026-12-31",
        buildingNo: null,
        streetName: "MAIN STREET",
        unitNo: null,
        buildingName: null,
        postalCode: "123456",
        telNo: "61234567",
      },
    ]);

    const result = await handleBcaRegisteredContractors({
      companyName: "ABC CONSTRUCTION PTE LTD",
      format: "json",
    });

    expect(result.structuredContent).toMatchObject({
      records: [
        expect.objectContaining({
          companyName: "ABC CONSTRUCTION PTE LTD",
          workhead: "CW01",
        }),
      ],
    });
  });
});
