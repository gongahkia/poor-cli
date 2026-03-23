import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  queryDatastoreExactMatches: vi.fn(),
}));

import { queryDatastoreExactMatches } from "../../datagov/client.js";
import { getCeaSalespersons } from "../client.js";

describe("CEA client", () => {
  beforeEach(() => {
    vi.mocked(queryDatastoreExactMatches).mockReset();
  });

  it("normalizes salesperson registry rows", async () => {
    vi.mocked(queryDatastoreExactMatches).mockResolvedValue([
      {
        salesperson_name: "JANE TAN",
        registration_no: "R123456A",
        registration_start_date: "2011-01-01",
        registration_end_date: "2026-12-31",
        estate_agent_name: "ERA REALTY NETWORK PTE LTD",
        estate_agent_license_no: "L3002382K",
      },
    ]);

    const result = await getCeaSalespersons({
      estateAgentName: "ERA REALTY NETWORK PTE LTD",
      limit: 10,
    });

    expect(result).toEqual([
      {
        salespersonName: "JANE TAN",
        registrationNo: "R123456A",
        registrationStartDate: "2011-01-01",
        registrationEndDate: "2026-12-31",
        estateAgentName: "ERA REALTY NETWORK PTE LTD",
        estateAgentLicenseNo: "L3002382K",
      },
    ]);
  });

  it("keeps datastore filters exact and case-insensitive after retrieval", async () => {
    const exactRow = {
      salesperson_name: "JANE TAN",
      registration_no: "R123456A",
      registration_start_date: "2011-01-01",
      registration_end_date: "2026-12-31",
      estate_agent_name: "ERA REALTY NETWORK PTE LTD",
      estate_agent_license_no: "L3002382K",
    };
    const broadRow = {
      salesperson_name: "JANE TAN JUNIOR",
      registration_no: "R999999Z",
      registration_start_date: "2015-01-01",
      registration_end_date: "2026-12-31",
      estate_agent_name: "ERA REALTY NETWORK PTE LTD",
      estate_agent_license_no: "L3002382K",
    };
    vi.mocked(queryDatastoreExactMatches).mockImplementation(async (_resourceId, options) => {
      expect(options?.exactMatch?.(exactRow)).toBe(true);
      expect(options?.exactMatch?.(broadRow)).toBe(false);
      return [exactRow];
    });

    const result = await getCeaSalespersons({
      salespersonName: "jane tan",
      limit: 10,
    });

    expect(result).toHaveLength(1);
    expect(result[0]?.salespersonName).toBe("JANE TAN");
    expect(vi.mocked(queryDatastoreExactMatches)).toHaveBeenCalledWith(
      "d_07c63be0f37e6e59c07a4ddc2fd87fcb",
      expect.objectContaining({
        matchLimit: 10,
        filters: {
          salesperson_name: { ilike: "jane tan" },
        },
      }),
    );
  });
});
