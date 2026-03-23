import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  queryDatastoreExactMatches: vi.fn(),
}));

import { queryDatastoreExactMatches } from "../../datagov/client.js";
import { getAcraEntities } from "../client.js";

describe("ACRA client", () => {
  beforeEach(() => {
    vi.mocked(queryDatastoreExactMatches).mockReset();
  });

  it("normalizes ACRA entity rows", async () => {
    vi.mocked(queryDatastoreExactMatches).mockResolvedValue([
      {
        uen: "201912345K",
        issuance_agency_id: "ACRA",
        entity_name: "ABC CONSTRUCTION PTE LTD",
        entity_type_description: "Local Company",
        business_constitution_description: "na",
        company_type_description: "Private Company Limited by Shares",
        paf_constitution_description: "na",
        entity_status_description: "Live Company",
        registration_incorporation_date: "2019-04-01",
        uen_issue_date: "2019-04-01",
        address_type: "LOCAL",
        block: "1",
        street_name: "MAIN STREET",
        level_no: "02",
        unit_no: "01",
        building_name: "ABC BUILDING",
        postal_code: "123456",
        other_address_line1: "na",
        other_address_line2: "na",
        account_due_date: "2026-04-01",
        annual_return_date: "2025-04-01",
        primary_ssic_code: "41001",
        primary_ssic_description: "GENERAL CONTRACTORS",
        primary_user_described_activity: "na",
        secondary_ssic_code: "na",
        secondary_ssic_description: "na",
        secondary_user_described_activity: "na",
        no_of_officers: "3",
      },
    ]);

    const result = await getAcraEntities({
      entityName: "ABC CONSTRUCTION PTE LTD",
      limit: 5,
    });

    expect(result).toEqual([
      expect.objectContaining({
        uen: "201912345K",
        entityName: "ABC CONSTRUCTION PTE LTD",
        businessConstitutionDescription: null,
        companyTypeDescription: "Private Company Limited by Shares",
        noOfOfficers: 3,
      }),
    ]);
  });

  it("searches all ACRA shards when only a UEN is provided", async () => {
    vi.mocked(queryDatastoreExactMatches)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          uen: "201912345K",
          issuance_agency_id: "ACRA",
          entity_name: "ABC CONSTRUCTION PTE LTD",
          entity_type_description: "Local Company",
          business_constitution_description: "na",
          company_type_description: "Private Company Limited by Shares",
          paf_constitution_description: "na",
          entity_status_description: "Live Company",
          registration_incorporation_date: "2019-04-01",
          uen_issue_date: "2019-04-01",
          address_type: "LOCAL",
          block: "1",
          street_name: "MAIN STREET",
          level_no: "02",
          unit_no: "01",
          building_name: "ABC BUILDING",
          postal_code: "123456",
          other_address_line1: "na",
          other_address_line2: "na",
          account_due_date: "2026-04-01",
          annual_return_date: "2025-04-01",
          primary_ssic_code: "41001",
          primary_ssic_description: "GENERAL CONTRACTORS",
          primary_user_described_activity: "na",
          secondary_ssic_code: "na",
          secondary_ssic_description: "na",
          secondary_user_described_activity: "na",
          no_of_officers: "3",
        },
      ]);

    const result = await getAcraEntities({
      uen: "201912345K",
      limit: 1,
    });

    expect(result).toHaveLength(1);
    expect(vi.mocked(queryDatastoreExactMatches)).toHaveBeenCalledTimes(2);
    expect(vi.mocked(queryDatastoreExactMatches)).toHaveBeenNthCalledWith(
      1,
      "d_8575e84912df3c28995b8e6e0e05205a",
      expect.objectContaining({
        filters: {
          uen: "201912345K",
        },
      }),
    );
  });
});
