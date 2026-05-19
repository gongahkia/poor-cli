import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/cea/client.js", () => ({
  getCeaSalespersons: vi.fn(),
}));

vi.mock("../../apis/bca/client.js", () => ({
  getBcaLicensedBuilders: vi.fn(),
  getBcaRegisteredContractors: vi.fn(),
}));

vi.mock("../../apis/boa/client.js", () => ({
  getBoaArchitects: vi.fn(),
  getBoaArchitectureFirms: vi.fn(),
}));

vi.mock("../../apis/acra/client.js", () => ({
  getAcraEntities: vi.fn(),
}));

vi.mock("../../apis/gebiz/client.js", () => ({
  getGeBIZTenders: vi.fn(),
}));

vi.mock("../../apis/hlb/client.js", () => ({
  getHlbHotels: vi.fn(),
}));

vi.mock("../../apis/hsa/client.js", () => ({
  getHsaHealthProductLicensees: vi.fn(),
  getHsaLicensedPharmacies: vi.fn(),
}));

import { getCeaSalespersons } from "../../apis/cea/client.js";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../../apis/bca/client.js";
import { getBoaArchitects, getBoaArchitectureFirms } from "../../apis/boa/client.js";
import { getAcraEntities } from "../../apis/acra/client.js";
import { getGeBIZTenders } from "../../apis/gebiz/client.js";
import { getHlbHotels } from "../../apis/hlb/client.js";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../../apis/hsa/client.js";
import { queryToolDefinitions } from "../query-tool.js";

const runQuery = async (input: Readonly<Record<string, unknown>>) => {
  const definition = queryToolDefinitions.find((tool) => tool.name === "sg_query");
  if (definition === undefined) {
    throw new Error("sg_query definition not found");
  }
  return definition.handler(input);
};

describe("sg_query CDD-only workflows", () => {
  beforeEach(() => {
    vi.mocked(getCeaSalespersons).mockReset();
    vi.mocked(getBcaLicensedBuilders).mockReset();
    vi.mocked(getBcaRegisteredContractors).mockReset();
    vi.mocked(getBoaArchitects).mockReset();
    vi.mocked(getBoaArchitectureFirms).mockReset();
    vi.mocked(getAcraEntities).mockReset();
    vi.mocked(getGeBIZTenders).mockReset();
    vi.mocked(getHlbHotels).mockReset();
    vi.mocked(getHsaHealthProductLicensees).mockReset();
    vi.mocked(getHsaLicensedPharmacies).mockReset();
  });

  it("returns unsupported for removed non-CDD public-data prompts", async () => {
    const result = await runQuery({
      query: "Give me a macro snapshot of Singapore",
      mode: "plan",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "unsupported",
      mode: "plan",
      reason: expect.stringContaining("CDD entity and sector diligence"),
      suggestion: expect.stringContaining("Singapore company name or UEN"),
    });
  });

  it("blocks CDD prompts without an entity or registry identifier", async () => {
    const result = await runQuery({
      query: "Run business diligence",
      mode: "plan",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "blocked",
      workflow: "business_dossier",
      blockers: expect.arrayContaining([
        expect.objectContaining({ field: "entityName", directTool: "sg_business_dossier" }),
        expect.objectContaining({ field: "uen", directTool: "sg_business_dossier" }),
      ]),
    });
  });

  it("plans the business dossier workflow for a named company", async () => {
    const result = await runQuery({
      query: "Business dossier for ABC CONSTRUCTION PTE LTD",
      mode: "plan",
    });

    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({
      status: "planned",
      workflow: "business_dossier",
      toolsUsed: ["sg_business_dossier"],
      steps: [
        expect.objectContaining({
          tool: "sg_business_dossier",
          input: expect.objectContaining({ entityName: "ABC CONSTRUCTION PTE LTD" }),
        }),
      ],
    });
  });

  it("executes the business registry diligence workflow for a named company", async () => {
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

    const result = await runQuery({
      query: "Run registry diligence for company ABC CONSTRUCTION PTE LTD workhead CW01",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "business_dossier",
      toolsUsed: ["sg_business_dossier"],
    });
    expect(vi.mocked(getAcraEntities)).toHaveBeenCalledWith(
      expect.objectContaining({ entityName: "ABC CONSTRUCTION PTE LTD", limit: 5 }),
    );
    expect(vi.mocked(getBcaRegisteredContractors)).toHaveBeenCalledWith(
      expect.objectContaining({ companyName: "ABC CONSTRUCTION PTE LTD", workhead: "CW01", limit: 5 }),
    );
    expect(vi.mocked(getCeaSalespersons)).not.toHaveBeenCalled();
  });

  it("executes the architecture-firm diligence workflow with BOA scope", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      { entityName: "DP Architects", uen: "199100765E", entityStatusDescription: "Live Company" },
    ] as never);
    vi.mocked(getBoaArchitectureFirms).mockResolvedValue([
      {
        firmName: "DP Architects",
        firmAddress: "6 RAFFLES BOULEVARD",
        firmPhone: "63372288",
        firmFax: null,
        firmEmail: "info@dpa.com.sg",
      },
    ] as never);
    vi.mocked(getBoaArchitects).mockResolvedValue([] as never);
    vi.mocked(getGeBIZTenders).mockResolvedValue([] as never);

    const result = await runQuery({
      query: "Architecture firm diligence for DP Architects",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "architecture_firm_diligence",
      toolsUsed: ["sg_business_dossier"],
    });
    expect(vi.mocked(getBoaArchitectureFirms)).toHaveBeenCalledWith(
      expect.objectContaining({ firmName: "DP Architects", limit: 5 }),
    );
  });

  it("executes the healthcare supplier diligence workflow with HSA scope", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
        uen: "201012345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getHsaHealthProductLicensees).mockResolvedValue([
      {
        companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
        licenseType: "Controlled Drugs - Wholesale Licence",
        activityType: null,
        dosageForm: null,
        expiryDate: "2027-07-20 00:00:00",
      },
    ] as never);
    vi.mocked(getHsaLicensedPharmacies).mockResolvedValue([] as never);
    vi.mocked(getGeBIZTenders).mockResolvedValue([] as never);

    const result = await runQuery({
      query: "Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "healthcare_supplier_diligence",
    });
    expect(vi.mocked(getHsaHealthProductLicensees)).toHaveBeenCalledWith(
      expect.objectContaining({ companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", limit: 10 }),
    );
  });

  it("executes the hotel-operator lookup workflow with HLB scope", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([] as never);
    vi.mocked(getHlbHotels).mockResolvedValue([
      {
        name: "RAFFLES HOTEL SINGAPORE",
        category: "hospitality",
        subcategory: "hotel",
        address: "1 BEACH ROAD",
        postalCode: "189673",
        lat: 1.2948,
        lng: 103.8546,
        sourceAgency: "Hotels Licensing Board",
        sourceDataset: "Hotels",
        sourceUrl: "https://data.gov.sg/collections/140/view",
        lastUpdatedAt: "2024-04-17T18:17:50+08:00",
        keeperName: "RAFFLES HOTEL SINGAPORE",
        totalRooms: 115,
        url: null,
        incCrc: "Y",
      },
    ] as never);

    const result = await runQuery({
      query: "Hotel operator lookup for company Raffles Hotel Singapore",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "hotel_operator_lookup",
      toolsUsed: ["sg_business_dossier"],
    });
    expect(vi.mocked(getHlbHotels)).toHaveBeenCalledWith(
      expect.objectContaining({ keeperName: "Raffles Hotel Singapore", limit: 5 }),
    );
  });

  it("executes sector-scoped diligence with procurement evidence", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      { entityName: "ABC CONSTRUCTION PTE LTD", uen: "201912345K", entityStatusDescription: "Live Company" },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([
      { companyName: "ABC CONSTRUCTION PTE LTD", classCode: "GB1", expiryDate: "2026-12-31" },
    ] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([
      { companyName: "ABC CONSTRUCTION PTE LTD", workhead: "CW01", grade: "C3", expiryDate: "2026-12-31" },
    ] as never);
    vi.mocked(getGeBIZTenders).mockResolvedValue([
      {
        agency: "MINDEF",
        tenderNo: "MINDEF000ETQ25000001",
        description: "Term contract for construction works",
        awardDate: "2025-01-15",
        status: "Awarded",
        supplierName: "ABC CONSTRUCTION PTE LTD",
        awardedAmount: 1250000,
        category: "Construction Works",
      },
    ] as never);

    const result = await runQuery({
      query: "Sector-scoped business diligence for company ABC CONSTRUCTION PTE LTD in construction procurement",
      mode: "execute",
    });

    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({
      status: "completed",
      workflow: "sector_scoped_business_diligence",
    });
    expect(vi.mocked(getGeBIZTenders)).toHaveBeenCalledWith(
      expect.objectContaining({ supplierName: "ABC CONSTRUCTION PTE LTD", limit: 10 }),
    );
  });
});
