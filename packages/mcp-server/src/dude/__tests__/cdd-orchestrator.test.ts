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

vi.mock("../../apis/tinyfish/client.js", () => ({
  getPeopleDiscovery: vi.fn(),
  getWebPresence: vi.fn(),
}));

import { getAcraEntities } from "../../apis/acra/client.js";
import { getBcaLicensedBuilders, getBcaRegisteredContractors } from "../../apis/bca/client.js";
import { getBoaArchitects, getBoaArchitectureFirms } from "../../apis/boa/client.js";
import { getCeaSalespersons } from "../../apis/cea/client.js";
import { getGeBIZTenders } from "../../apis/gebiz/client.js";
import { getHlbHotels } from "../../apis/hlb/client.js";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../../apis/hsa/client.js";
import { getPeopleDiscovery, getWebPresence } from "../../apis/tinyfish/client.js";
import { runCddOrchestrator } from "../cdd-orchestrator.js";

const resetRegistryMocks = () => {
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

describe("CDD orchestrator", () => {
  beforeEach(() => {
    resetRegistryMocks();
    vi.mocked(getWebPresence).mockReset();
    vi.mocked(getPeopleDiscovery).mockReset();
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([]);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([]);
    vi.mocked(getBoaArchitects).mockResolvedValue([]);
    vi.mocked(getBoaArchitectureFirms).mockResolvedValue([]);
    vi.mocked(getCeaSalespersons).mockResolvedValue([]);
    vi.mocked(getGeBIZTenders).mockResolvedValue([]);
    vi.mocked(getHlbHotels).mockResolvedValue([]);
    vi.mocked(getHsaHealthProductLicensees).mockResolvedValue([]);
    vi.mocked(getHsaLicensedPharmacies).mockResolvedValue([]);
    vi.mocked(getWebPresence).mockResolvedValue({
      configured: false,
      limits: ["TinyFish Search is not configured on the server."],
      possibleOfficialWebsite: null,
      query: "ABC CONSTRUCTION PTE LTD 201912345K",
      results: [],
    });
    vi.mocked(getPeopleDiscovery).mockResolvedValue({
      configured: false,
      entityName: "ABC CONSTRUCTION PTE LTD",
      limits: ["TinyFish Search is not configured on the server."],
      query: "\"ABC CONSTRUCTION\" Singapore employees leadership directors LinkedIn",
      results: [],
      suggestedActions: [],
      uen: "201912345K",
    });
    delete process.env["OPENAI_API_KEY"];
    delete process.env["ANTHROPIC_API_KEY"];
    delete process.env["GOOGLE_GENERATIVE_AI_API_KEY"];
  });

  it("returns a complete orchestrator envelope and reruns official modules when web sector hints add scope", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        entityStatusDescription: "Live Company",
        primarySsicCode: "41001",
        primarySsicDescription: "GENERAL CONTRACTORS",
        uen: "201912345K",
      },
    ] as never);
    vi.mocked(getWebPresence).mockResolvedValue({
      configured: true,
      limits: ["Fixture web discovery."],
      possibleOfficialWebsite: "https://abc.example",
      query: "ABC CONSTRUCTION PTE LTD 201912345K",
      results: [{
        position: 1,
        siteName: "ABC",
        snippet: "ABC provides architecture and building contractor services in Singapore.",
        title: "ABC architecture and construction",
        url: "https://abc.example",
      }],
    });
    vi.mocked(getBoaArchitectureFirms).mockResolvedValue([
      {
        firmAddress: "1 MAIN STREET",
        firmEmail: "info@abc.example",
        firmFax: null,
        firmName: "ABC CONSTRUCTION PTE LTD",
        firmPhone: "61234567",
      },
    ] as never);

    const response = await runCddOrchestrator({ entityName: "ABC CONSTRUCTION PTE LTD" });

    expect(response).toMatchObject({
      dossier: expect.objectContaining({
        records: expect.objectContaining({
          resolution: expect.objectContaining({
            selectedModules: expect.arrayContaining(["acra", "bca", "boa"]),
          }),
        }),
      }),
      memo: expect.objectContaining({ status: "unavailable" }),
      orchestration: expect.objectContaining({
        acraSectorHints: ["construction"],
        effectiveSectorHints: expect.arrayContaining(["construction", "architecture"]),
        officialModules: expect.arrayContaining(["acra", "bca", "boa"]),
        reranDossierForWebSectorHints: true,
        status: "ready",
        strategy: "acra_then_sector_then_supplemental_memo",
        webSectorHints: expect.arrayContaining(["construction", "architecture"]),
      }),
      peopleDiscovery: expect.objectContaining({ configured: false }),
      webPresence: expect.objectContaining({ configured: true }),
    });
    expect(response.orchestration.stages).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "acra_identity", status: "completed" }),
      expect.objectContaining({ id: "official_modules", status: "completed" }),
      expect.objectContaining({ id: "ai_memo", status: "unavailable" }),
    ]));
    expect(vi.mocked(getAcraEntities)).toHaveBeenCalledTimes(2);
    expect(vi.mocked(getBoaArchitectureFirms)).toHaveBeenCalled();
  });

  it("stops after ACRA identity when no canonical entity is resolved", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([]);

    const response = await runCddOrchestrator({ uen: "201912345K" });

    expect(response.orchestration).toMatchObject({
      status: "identity_not_resolved",
      webSectorHints: [],
      reranDossierForWebSectorHints: false,
    });
    expect(response.orchestration.stages).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "acra_identity", status: "blocked" }),
      expect.objectContaining({ id: "official_modules", status: "skipped" }),
    ]));
    expect(response.webPresence.limits).toEqual(expect.arrayContaining([
      expect.stringContaining("ACRA did not return a canonical entity record"),
    ]));
    expect(vi.mocked(getWebPresence)).not.toHaveBeenCalled();
    expect(vi.mocked(getPeopleDiscovery)).not.toHaveBeenCalled();
  });
});
