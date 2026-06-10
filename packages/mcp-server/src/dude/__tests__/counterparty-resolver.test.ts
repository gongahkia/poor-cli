import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/acra/client.js", () => ({
  getAcraEntities: vi.fn(),
}));

vi.mock("../../apis/bca/client.js", () => ({
  getBcaLicensedBuilders: vi.fn(),
  getBcaRegisteredContractors: vi.fn(),
}));

vi.mock("../../apis/boa/client.js", () => ({
  getBoaArchitects: vi.fn(),
  getBoaArchitectureFirms: vi.fn(),
}));

vi.mock("../../apis/cea/client.js", () => ({
  getCeaSalespersons: vi.fn(),
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

import { getAcraEntities } from "../../apis/acra/client.js";
import { getBcaLicensedBuilders, getBcaRegisteredContractors } from "../../apis/bca/client.js";
import { getBoaArchitects, getBoaArchitectureFirms } from "../../apis/boa/client.js";
import { getCeaSalespersons } from "../../apis/cea/client.js";
import { getGeBIZTenders } from "../../apis/gebiz/client.js";
import { getHlbHotels } from "../../apis/hlb/client.js";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../../apis/hsa/client.js";
import { resolveCounterparty } from "../counterparty-resolver.js";

const resetMocks = () => {
  vi.mocked(getAcraEntities).mockReset();
  vi.mocked(getBcaLicensedBuilders).mockReset();
  vi.mocked(getBcaRegisteredContractors).mockReset();
  vi.mocked(getBoaArchitects).mockReset();
  vi.mocked(getBoaArchitectureFirms).mockReset();
  vi.mocked(getCeaSalespersons).mockReset();
  vi.mocked(getGeBIZTenders).mockReset();
  vi.mocked(getHlbHotels).mockReset();
  vi.mocked(getHsaHealthProductLicensees).mockReset();
  vi.mocked(getHsaLicensedPharmacies).mockReset();
};

const resolveEmptyRegistries = () => {
  vi.mocked(getBcaLicensedBuilders).mockResolvedValue([]);
  vi.mocked(getBcaRegisteredContractors).mockResolvedValue([]);
  vi.mocked(getBoaArchitects).mockResolvedValue([]);
  vi.mocked(getBoaArchitectureFirms).mockResolvedValue([]);
  vi.mocked(getCeaSalespersons).mockResolvedValue([]);
  vi.mocked(getGeBIZTenders).mockResolvedValue([]);
  vi.mocked(getHlbHotels).mockResolvedValue([]);
  vi.mocked(getHsaHealthProductLicensees).mockResolvedValue([]);
  vi.mocked(getHsaLicensedPharmacies).mockResolvedValue([]);
};

describe("counterparty resolver", () => {
  beforeEach(() => {
    resetMocks();
    resolveEmptyRegistries();
  });

  it("resolves exact UENs without fuzzy identifier matching", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "DBS BANK LTD",
        entityStatusDescription: "Live Company",
        entityTypeDescription: "Local Company",
        uen: "196800306E",
      },
    ] as never);

    const result = await resolveCounterparty({ identifier: "196800306E" });

    expect(result.status).toBe("resolved");
    expect(result.selectedCandidate).toMatchObject({
      entityName: "DBS BANK LTD",
      matchMethod: "exact_identifier",
      uen: "196800306E",
    });
    expect(vi.mocked(getAcraEntities)).toHaveBeenCalledWith({ uen: "196800306E", limit: 1 });
  });

  it("requires confirmation when a shorthand name has multiple plausible official matches", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "DBS BANK LTD",
        entityStatusDescription: "Live Company",
        entityTypeDescription: "Local Company",
        uen: "196800306E",
      },
      {
        entityName: "DBS GROUP HOLDINGS LTD",
        entityStatusDescription: "Live Company",
        entityTypeDescription: "Local Company",
        uen: "199901152M",
      },
    ] as never);

    const result = await resolveCounterparty({ identifier: "dbs" });

    expect(result.status).toBe("needs_confirmation");
    expect(result.candidates.map((candidate) => candidate.entityName)).toEqual([
      "DBS BANK LTD",
      "DBS GROUP HOLDINGS LTD",
    ]);
    expect(result.confidenceBlockers.join(" ")).toContain("confirmation");
  });

  it("auto-resolves a single high-confidence official candidate", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "DP ARCHITECTS PTE LTD",
        entityStatusDescription: "Live Company",
        entityTypeDescription: "Local Company",
        uen: "199900001A",
      },
    ] as never);

    const result = await resolveCounterparty({ identifier: "dp architects" });

    expect(result.status).toBe("resolved");
    expect(result.selectedCandidate).toMatchObject({
      entityName: "DP ARCHITECTS PTE LTD",
      uen: "199900001A",
    });
  });
});
