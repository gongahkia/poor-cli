import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/moe/client.js", () => ({
  MOE_SCHOOLS_RESOURCE_ID: "d_688b934f82c1059ed0a6993d2a829089",
  getSchools: vi.fn(),
}));

vi.mock("../../apis/moh/client.js", () => ({
  MOH_HEALTHCARE_FACILITIES_RESOURCE_ID: "d_23b6e552fdce728e1e9fa5a5103d0205",
  getHealthcareFacilities: vi.fn(),
}));

import { getSchools } from "../../apis/moe/client.js";
import { getHealthcareFacilities } from "../../apis/moh/client.js";
import { handleMoeSchools } from "../moe-tools.js";
import { handleMohFacilities } from "../moh-tools.js";

describe("directory tool metadata envelopes", () => {
  beforeEach(() => {
    vi.mocked(getSchools).mockReset();
    vi.mocked(getHealthcareFacilities).mockReset();
  });

  it("adds provenance, freshness, and limits for MOE directory responses", async () => {
    vi.mocked(getSchools).mockResolvedValue([
      {
        name: "SAMPLE PRIMARY SCHOOL",
        url: "https://www.moe.gov.sg",
        address: "1 SAMPLE ROAD",
        postalCode: "560123",
        telephone: "61234567",
        level: "PRIMARY",
        zone: "NORTH",
        nature: "GOVT",
        type: "MIXED",
      },
    ]);

    const result = await handleMoeSchools({ level: "PRIMARY", zone: "NORTH", format: "json" });
    expect(result.structuredContent).toMatchObject({
      records: [expect.objectContaining({ name: "SAMPLE PRIMARY SCHOOL" })],
      provenance: {
        source: "data.gov.sg datastore",
        publisher: "Ministry of Education",
        resourceId: "d_688b934f82c1059ed0a6993d2a829089",
      },
      freshness: {
        sourceTimestamp: null,
      },
      limits: {
        defaultLimit: 50,
        maxLimit: 200,
        supportedFilters: ["level", "zone", "name"],
      },
    });
    expect(result.structuredContent).toMatchObject({
      freshness: { observedAt: expect.any(String) },
    });
  });

  it("adds provenance, freshness, and limits for MOH directory responses", async () => {
    vi.mocked(getHealthcareFacilities).mockResolvedValue([
      {
        name: "SAMPLE GENERAL HOSPITAL",
        code: "H0001",
        type: "HOSPITAL",
        street: "SAMPLE STREET",
        block: "1",
        postalCode: "119077",
        telephone: "67720000",
      },
    ]);

    const result = await handleMohFacilities({ type: "HOSPITAL", postalCode: "119077", format: "json" });
    expect(result.structuredContent).toMatchObject({
      records: [expect.objectContaining({ name: "SAMPLE GENERAL HOSPITAL" })],
      provenance: {
        source: "data.gov.sg datastore",
        publisher: "Ministry of Health",
        resourceId: "d_23b6e552fdce728e1e9fa5a5103d0205",
      },
      freshness: {
        sourceTimestamp: null,
      },
      limits: {
        defaultLimit: 50,
        maxLimit: 200,
        supportedFilters: ["type", "name", "postalCode"],
      },
    });
    expect(result.structuredContent).toMatchObject({
      freshness: { observedAt: expect.any(String) },
    });
  });
});
