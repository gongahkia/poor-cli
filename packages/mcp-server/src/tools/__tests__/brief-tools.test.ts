import { beforeEach, describe, expect, it, vi } from "vitest";
import { BriefArtifactSchema, MasDataset, type ToolResult } from "@swee-sg/shared";

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

vi.mock("../../apis/govfeeds/client.js", () => ({
  getGovFeedItems: vi.fn(),
}));

vi.mock("../../apis/hdb/client.js", () => ({
  getHdbResalePrices: vi.fn(),
}));

vi.mock("../../apis/hlb/client.js", () => ({
  getHlbHotels: vi.fn(),
}));

vi.mock("../../apis/hsa/client.js", () => ({
  getHsaHealthProductLicensees: vi.fn(),
  getHsaLicensedPharmacies: vi.fn(),
}));

vi.mock("../../apis/lta/client.js", () => ({
  getBusArrivals: vi.fn(),
  getTrainAlerts: vi.fn(),
  getTrafficIncidents: vi.fn(),
}));

vi.mock("../../apis/nea/client.js", () => ({
  getAirQuality: vi.fn(),
  getForecast2Hr: vi.fn(),
  getRainfall: vi.fn(),
}));

vi.mock("../../apis/onemap/client.js", () => ({
  geocode: vi.fn(),
}));

vi.mock("../../apis/singstat/client.js", () => ({
  getTableData: vi.fn(),
}));

vi.mock("../../apis/ura/client.js", () => ({
  getPropertyTransactions: vi.fn(),
}));

vi.mock("../mas-tools.js", () => ({
  fetchNormalizedMasRecords: vi.fn(),
}));

vi.mock("../ura-tools.js", () => ({
  lookupPlanningArea: vi.fn(),
}));

import { getAcraEntities } from "../../apis/acra/client.js";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../../apis/bca/client.js";
import { getBoaArchitects, getBoaArchitectureFirms } from "../../apis/boa/client.js";
import { getCeaSalespersons } from "../../apis/cea/client.js";
import { getGeBIZTenders } from "../../apis/gebiz/client.js";
import { getGovFeedItems } from "../../apis/govfeeds/client.js";
import { getHdbResalePrices } from "../../apis/hdb/client.js";
import { getHlbHotels } from "../../apis/hlb/client.js";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../../apis/hsa/client.js";
import {
  getBusArrivals,
  getTrainAlerts,
  getTrafficIncidents,
} from "../../apis/lta/client.js";
import {
  getAirQuality,
  getForecast2Hr,
  getRainfall,
} from "../../apis/nea/client.js";
import { getTableData as getSingStatTableData } from "../../apis/singstat/client.js";
import { getPropertyTransactions } from "../../apis/ura/client.js";
import { fetchNormalizedMasRecords } from "../mas-tools.js";
import { lookupPlanningArea } from "../ura-tools.js";
import {
  handleBusinessDossier,
  handleEnvironmentBrief,
  handleMacroBrief,
  handlePropertyBrief,
  handleTransportBrief,
} from "../brief-tools.js";

const parseBrief = (resultText: string) => {
  return BriefArtifactSchema.parse(JSON.parse(resultText));
};

type ParsedBriefArtifact = ReturnType<(typeof BriefArtifactSchema)["parse"]>;

const getText = (result: ToolResult): string => {
  return result.content.find((item): item is Extract<ToolResult["content"][number], { type: "text" }> => item.type === "text")?.text ?? "";
};

const expectMarkdownSections = (text: string) => {
  expect(text).toContain("### Sources");
  expect(text).toContain("### Freshness");
  expect(text).toContain("### What This Does Not Do");
};

const expectBriefQualityContract = (
  payload: ParsedBriefArtifact,
  options: Readonly<{
    title: string;
    requiredRecords: readonly string[];
    requiredTools: readonly string[];
    requiredLimitCodes: readonly string[];
  }>,
) => {
  expect(payload.title).toBe(options.title);
  expect(payload.summary.length).toBeGreaterThanOrEqual(3);
  expect(payload.evidence.length).toBeGreaterThanOrEqual(2);
  expect(payload.provenance.map((item) => item.tool)).toEqual(expect.arrayContaining([...options.requiredTools]));
  expect(payload.freshness.length).toBeGreaterThanOrEqual(options.requiredTools.length);
  expect(payload.limits.map((item) => item.code)).toEqual(expect.arrayContaining([...options.requiredLimitCodes]));
  expect(Object.keys(payload.records)).toEqual(expect.arrayContaining([...options.requiredRecords]));
  expect(payload.provenance.every((item) => item.source.length > 0 && item.coverage.length > 0)).toBe(true);
  expect(payload.freshness.every((item) => item.source.length > 0 && item.observedAt.length > 0)).toBe(true);
};

describe("brief tools", () => {
  beforeEach(() => {
    vi.mocked(getAcraEntities).mockReset();
    vi.mocked(getBcaLicensedBuilders).mockReset();
    vi.mocked(getBcaRegisteredContractors).mockReset();
    vi.mocked(getBoaArchitects).mockReset();
    vi.mocked(getBoaArchitectureFirms).mockReset();
    vi.mocked(getCeaSalespersons).mockReset();
    vi.mocked(getGeBIZTenders).mockReset();
    vi.mocked(getGovFeedItems).mockReset();
    vi.mocked(getHdbResalePrices).mockReset();
    vi.mocked(getHlbHotels).mockReset();
    vi.mocked(getHsaHealthProductLicensees).mockReset();
    vi.mocked(getHsaLicensedPharmacies).mockReset();
    vi.mocked(getBusArrivals).mockReset();
    vi.mocked(getTrainAlerts).mockReset();
    vi.mocked(getTrafficIncidents).mockReset();
    vi.mocked(getAirQuality).mockReset();
    vi.mocked(getForecast2Hr).mockReset();
    vi.mocked(getRainfall).mockReset();
    vi.mocked(getSingStatTableData).mockReset();
    vi.mocked(getPropertyTransactions).mockReset();
    vi.mocked(fetchNormalizedMasRecords).mockReset();
    vi.mocked(lookupPlanningArea).mockReset();
    vi.mocked(getGovFeedItems).mockResolvedValue({
      cached: false,
      channelTitle: "Mock feed",
      feed: {
        family: "mock",
        id: "mock_feed",
        sourceAgency: "Mock agency",
        sourceUrl: "https://example.test/feed",
        title: "Mock feed",
      },
      observedAt: "2026-05-17T00:00:00.000Z",
      records: [],
    } as never);
    delete process.env["OPENSANCTIONS_API_KEY"];
    delete process.env["OPENCORPORATES_API_TOKEN"];
  });

  it("returns the expanded business dossier envelope", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
        noOfOfficers: 3,
        annualReturnDate: "2026-03-01",
      },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([
      {
        companyName: "ABC CONSTRUCTION PTE LTD",
        classCode: "GB1",
        expiryDate: "2026-12-31",
      },
    ] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([
      {
        companyName: "ABC CONSTRUCTION PTE LTD",
        workhead: "CW01",
        expiryDate: "2026-12-31",
      },
    ] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "ABC CONSTRUCTION PTE LTD",
      format: "json",
    });
    const jsonText = getText(jsonResult);
    const payload = parseBrief(jsonText);

    expect(payload.title).toBe("Business Dossier");
    expectBriefQualityContract(payload, {
      title: "Business Dossier",
      requiredRecords: ["resolution", "quality", "handoff"],
      requiredTools: ["sg_acra_entities"],
      requiredLimitCodes: ["PUBLIC_REGISTRY_SCOPE"],
    });
    expect(payload.provenance).toHaveLength(1);
    expect(payload.provenance[0]).toMatchObject({
      evidenceType: "official_registry",
      sourceUrl: "https://www.acra.gov.sg/resources/open-data-initiative/",
    });
    expect(payload.freshness).toHaveLength(1);
    expect(payload.limits.length).toBeGreaterThan(0);
    expect((payload.records["quality"] as Record<string, unknown>)["dossierConfidence"]).toMatchObject({
      level: "high",
    });
    expect((payload.records["handoff"] as Record<string, unknown>)["markdown"]).toEqual(
      expect.stringContaining("## Due Diligence Handoff"),
    );

    const markdownResult = await handleBusinessDossier({
      entityName: "ABC CONSTRUCTION PTE LTD",
      format: "markdown",
    });
    expectMarkdownSections(getText(markdownResult));
  });

  it("returns optional context IDs when requested", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
        noOfOfficers: 3,
        annualReturnDate: "2026-03-01",
      },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([] as never);

    const result = await handleBusinessDossier({
      entityName: "ABC CONSTRUCTION PTE LTD",
      format: "json",
      includeContextIds: true,
    });

    expect(result.structuredContent).toMatchObject({
      contextIds: {
        traceId: expect.stringMatching(
          /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
        ),
        requestId: expect.stringMatching(
          /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
        ),
      },
    });
  });

  it("defaults plain UEN dossiers to ACRA only and does not imply CEA coverage", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);

    const jsonResult = await handleBusinessDossier({
      uen: "201912345K",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const resolution = payload.records["resolution"] as Record<string, unknown>;
    const quality = payload.records["quality"] as Record<string, unknown>;

    expect(resolution).toMatchObject({
      selectedModules: ["acra"],
      searchedModules: ["acra"],
      matchedModules: ["acra"],
      unmatchedModules: [],
      unsearchedModules: [],
    });
    expect(payload.provenance.map((item) => item.tool)).toEqual(["sg_acra_entities"]);
    expect(payload.provenance[0]).toMatchObject({
      evidenceType: "official_registry",
      sourceUrl: "https://www.acra.gov.sg/resources/open-data-initiative/",
    });
    expect(payload.freshness.map((item) => item.source)).toEqual(["ACRA"]);
    expect(payload.gaps.map((gap) => gap.code)).not.toContain("CEA_NO_MATCH");
    expect(payload.matchConfidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "ACRA", confidence: "exact", matchedOn: "uen" }),
      ]),
    );
    expect(quality["dossierConfidence"]).toMatchObject({
      level: "high",
      score: 1,
      identity: {
        level: "high",
        score: 1,
        primarySource: "ACRA",
        matchedOn: "uen",
      },
      coverage: {
        selectedModules: ["acra"],
        searchedModules: ["acra"],
        matchedModules: ["acra"],
        unmatchedModules: [],
        unsearchedModules: [],
        score: 1,
      },
    });
  });

  it("derives deterministic prioritized analyst follow-ups from evidence gaps", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([]);

    const firstResult = await handleBusinessDossier({
      uen: "201912345K",
      format: "json",
    });
    const secondResult = await handleBusinessDossier({
      uen: "201912345K",
      format: "json",
    });
    const firstPayload = parseBrief(getText(firstResult));
    const secondPayload = parseBrief(getText(secondResult));
    const followUps = firstPayload.analystFollowUps ?? [];

    expect(followUps.length).toBeGreaterThan(0);
    expect(followUps).toEqual(secondPayload.analystFollowUps);
    expect(followUps[0]).toMatchObject({
      priority: "critical",
      category: "identity_confidence",
      tool: "sg_acra_entities",
      evidenceBasis: [expect.objectContaining({
        kind: expect.stringMatching(/source_gap|confidence_blocker/),
        ref: expect.stringMatching(/^(sourceCoverage\.acra|gap\.ACRA_NO_MATCH)$/),
      })],
    });
    expect(followUps.every((followUp) => followUp.evidenceBasis.length > 0)).toBe(true);
    expect(JSON.stringify(followUps)).not.toMatch(/\b(approve|reject|clear|safe)\b/i);
  });

  it("keeps exact ACRA identity confidence high when explicit BCA coverage has no match", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([] as never);

    const jsonResult = await handleBusinessDossier({
      uen: "201912345K",
      modules: ["acra", "bca"],
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const resolution = payload.records["resolution"] as Record<string, unknown>;
    const quality = payload.records["quality"] as Record<string, unknown>;

    expect(resolution).toMatchObject({
      selectedModules: ["acra", "bca"],
      searchedModules: ["acra", "bca"],
      matchedModules: ["acra"],
      unmatchedModules: ["bca"],
    });
    expect(quality["dossierConfidence"]).toMatchObject({
      level: "high",
      score: 1,
      identity: {
        level: "high",
        score: 1,
        primarySource: "ACRA",
        matchedOn: "uen",
      },
      coverage: {
        searchedModules: ["acra", "bca"],
        matchedModules: ["acra"],
        unmatchedModules: ["bca"],
        score: 0.5,
      },
    });
    expect(payload.matchConfidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "ACRA", confidence: "exact", matchedOn: "uen" }),
        expect.objectContaining({ source: "BCA licensed builders", confidence: "no-match" }),
        expect.objectContaining({ source: "BCA registered contractors", confidence: "no-match" }),
      ]),
    );
    expect(payload.riskFlags).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "PARTIAL_MODULE_COVERAGE", severity: "medium", source: "Resolver" }),
      ]),
    );
  });

  it("adds a source coverage matrix for fully checked official families", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([
      { companyName: "ABC CONSTRUCTION PTE LTD", classCode: "GB1" },
    ] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([
      { companyName: "ABC CONSTRUCTION PTE LTD", workhead: "CW01" },
    ] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "ABC CONSTRUCTION PTE LTD",
      modules: ["acra", "bca"],
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect(payload.sourceCoverage).toEqual(expect.arrayContaining([
      expect.objectContaining({
        coverageLevel: "full",
        family: "acra",
        recordCount: 1,
        status: "checked",
      }),
      expect.objectContaining({
        coverageLevel: "full",
        family: "bca",
        recordCount: 2,
        status: "checked",
      }),
    ]));
  });

  it("represents partial family coverage when one source in a checked family is unavailable", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockRejectedValue(new Error("BCA builder feed timeout"));
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([
      { companyName: "ABC CONSTRUCTION PTE LTD", workhead: "CW01" },
    ] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "ABC CONSTRUCTION PTE LTD",
      modules: ["acra", "bca"],
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect(payload.sourceCoverage).toEqual(expect.arrayContaining([
      expect.objectContaining({
        coverageLevel: "partial",
        family: "bca",
        gapCodes: expect.arrayContaining(["BCA_BUILDERS_UNAVAILABLE"]),
        recordCount: 1,
        status: "checked",
        reason: expect.stringContaining("Partial coverage is not clearance"),
      }),
    ]));
  });

  it("keeps skipped and credential-blocked sources as gaps instead of clean results", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "ABC CONSTRUCTION PTE LTD",
      includeExternalDiligence: true,
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect(payload.sourceCoverage).toEqual(expect.arrayContaining([
      expect.objectContaining({
        family: "opensanctions",
        status: "credential_blocked",
        reason: expect.stringContaining("confidence blocker"),
      }),
      expect.objectContaining({
        family: "opencorporates",
        status: "credential_blocked",
        reason: expect.stringContaining("confidence blocker"),
      }),
      expect.objectContaining({
        family: "web_presence",
        status: "skipped",
        reason: expect.stringContaining("was not run"),
      }),
    ]));
    const coverageText = JSON.stringify(payload.sourceCoverage);
    expect(coverageText).not.toMatch(/clean result|clearance claim|sanctioned-free/i);
    expect(coverageText).toMatch(/not .*clearance|not proof|No conclusion is drawn/i);
  });

  it("infers sector modules from ACRA SSIC evidence and explains module reasons", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
        primarySsicCode: "41001",
        primarySsicDescription: "GENERAL CONTRACTORS",
      },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([
      {
        companyName: "ABC CONSTRUCTION PTE LTD",
        classCode: "GB1",
        expiryDate: "2026-12-31",
      },
    ] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "ABC CONSTRUCTION PTE LTD",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const resolution = payload.records["resolution"] as Record<string, unknown>;

    expect(resolution).toMatchObject({
      selectedModules: ["acra", "bca"],
      effectiveSectorHints: ["construction"],
      inferredSectors: [
        expect.objectContaining({
          sector: "construction",
          source: "ACRA",
          evidence: expect.stringContaining("41001"),
          modules: ["bca"],
        }),
      ],
      searchedModules: ["acra", "bca"],
      matchedModules: ["acra", "bca"],
    });
    expect(resolution["moduleReasons"]).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          module: "acra",
          status: "matched",
          selectedBy: ["default"],
          searched: true,
          matched: true,
        }),
        expect.objectContaining({
          module: "bca",
          status: "matched",
          selectedBy: ["inferred_sector"],
          inferredSectors: ["construction"],
          searched: true,
          matched: true,
        }),
        expect.objectContaining({
          module: "cea",
          status: "skipped",
          searched: false,
          matched: false,
        }),
      ]),
    );
    expect(payload.provenance).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          tool: "sg_bca_licensed_builders",
          evidenceType: "official_registry",
          sourceUrl: "https://developers.data.gov.sg/datasets?resultId=d_19573c579879be15623f2e1e3854926d",
        }),
      ]),
    );
  });

  it("supports explicit module selection, sector hints, and unmatched module reporting", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "DESIGN LAB PTE LTD",
        uen: "202012345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getBoaArchitectureFirms).mockResolvedValue([
      {
        firmName: "DESIGN LAB PTE LTD",
        firmAddress: "1 MAIN STREET",
        firmPhone: "61234567",
        firmFax: null,
        firmEmail: "hello@designlab.sg",
      },
    ] as never);
    vi.mocked(getBoaArchitects).mockResolvedValue([] as never);
    vi.mocked(getGeBIZTenders).mockResolvedValue([] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "DESIGN LAB PTE LTD",
      modules: ["acra", "boa", "gebiz"],
      sectorHints: ["architecture", "procurement"],
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const resolution = payload.records["resolution"] as Record<string, unknown>;
    const quality = payload.records["quality"] as Record<string, unknown>;

    expect(resolution).toMatchObject({
      selectedModules: ["acra", "boa", "gebiz"],
      matchedModules: ["acra", "boa"],
      unmatchedModules: ["gebiz"],
    });
    expect(payload.provenance).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ tool: "sg_boa_architecture_firms" }),
        expect.objectContaining({ tool: "sg_gebiz_tenders", recordCount: 0 }),
      ]),
    );
    expect(payload.matchConfidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "BOA architecture firms", confidence: "name-exact" }),
        expect.objectContaining({ source: "GeBIZ", confidence: "no-match" }),
      ]),
    );
    expect(quality["dossierConfidence"]).toMatchObject({
      level: "high",
      coverage: {
        selectedModules: ["acra", "boa", "gebiz"],
        matchedModules: ["acra", "boa"],
        unmatchedModules: ["gebiz"],
        score: 0.67,
      },
    });
    expect(payload.riskFlags).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "PARTIAL_MODULE_COVERAGE", severity: "medium", source: "Resolver" }),
      ]),
    );
    expect(resolution["sectorWorkflowGuide"]).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          sector: "architecture",
          retainedTools: expect.arrayContaining(["sg_boa_architecture_firms", "sg_boa_architects"]),
          requiredIdentifiers: expect.arrayContaining(["Architecture firm name"]),
        }),
        expect.objectContaining({
          sector: "procurement",
          followUpPrompts: expect.arrayContaining([
            expect.stringContaining("supplier name"),
          ]),
        }),
      ]),
    );
  });

  it("marks selected sector modules as needs-identifier when required inputs are missing", async () => {
    const jsonResult = await handleBusinessDossier({
      modules: ["hsa"],
      registrationNo: "R123456A",
      sectorHints: ["healthcare"],
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const resolution = payload.records["resolution"] as Record<string, unknown>;

    expect(resolution).toMatchObject({
      selectedModules: ["hsa"],
      searchedModules: [],
      unsearchedModules: ["hsa"],
      moduleReasons: expect.arrayContaining([
        expect.objectContaining({
          module: "hsa",
          status: "needs_identifier",
          selectedBy: ["explicit_module", "sector_hint"],
          searched: false,
          matched: false,
          requiredIdentifiers: expect.arrayContaining(["Company or pharmacy name"]),
        }),
      ]),
    });
    expect(payload.gaps).toEqual(expect.arrayContaining([
      expect.objectContaining({
        code: "HSA_NEEDS_IDENTIFIER",
        message: expect.stringContaining("Company or pharmacy name"),
      }),
    ]));
    expect(payload.sourceCoverage).toEqual(expect.arrayContaining([
      expect.objectContaining({
        family: "hsa",
        status: "skipped",
        reason: expect.stringContaining("unchecked sector gap"),
      }),
    ]));
    expect(payload.analystFollowUps).toEqual(expect.arrayContaining([
      expect.objectContaining({
        category: "sector_gap",
        action: expect.stringContaining("Company or pharmacy name"),
      }),
    ]));
  });

  it("uses the company name as the CEA estate-agent search input when CEA is selected broadly", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "DESIGN LAB PTE LTD",
        uen: "202012345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getCeaSalespersons).mockResolvedValue([
      {
        estateAgentName: "DESIGN LAB PTE LTD",
        estateAgentLicenseNo: "L3000001A",
        salespersonName: "Jane Tan",
      },
    ] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "DESIGN LAB PTE LTD",
      modules: ["acra", "cea"],
      sectorHints: ["real_estate"],
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const resolution = payload.records["resolution"] as Record<string, unknown>;

    expect(getCeaSalespersons).toHaveBeenCalledWith(expect.objectContaining({
      estateAgentName: "DESIGN LAB PTE LTD",
      limit: 5,
    }));
    expect(resolution).toMatchObject({
      selectedModules: ["acra", "cea"],
      searchedModules: ["acra", "cea"],
      matchedModules: ["acra", "cea"],
    });
    expect(payload.matchConfidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "CEA", confidence: "name-exact", matchedOn: "estateAgentName" }),
      ]),
    );
  });

  it("adds a high-severity no-module-match risk flag when no selected module returns evidence", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "UNKNOWN ENTITY PTE LTD",
      modules: ["acra", "bca"],
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const quality = payload.records["quality"] as Record<string, unknown>;

    expect(payload.riskFlags).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "NO_MODULE_MATCHES", severity: "high", source: "Resolver" }),
      ]),
    );
    expect(quality["dossierConfidence"]).toMatchObject({
      level: "low",
      score: 0,
      identity: {
        level: "low",
        score: 0,
        primarySource: "ACRA",
      },
      coverage: {
        matchedModules: [],
        unmatchedModules: ["acra", "bca"],
        score: 0,
      },
    });
  });

  it("does not emit ACRA no-match risk flags when the dossier only searched hotel evidence", async () => {
    vi.mocked(getHlbHotels).mockResolvedValue([
      {
        name: "Marina Bay Sands",
        category: "hospitality",
        subcategory: "hotel",
        address: "10 BAYFRONT AVENUE",
        postalCode: "018956",
        lat: 1.2834,
        lng: 103.8607,
        sourceAgency: "Hotels Licensing Board",
        sourceDataset: "Hotels",
        sourceUrl: "https://data.gov.sg/collections/140/view",
        lastUpdatedAt: "2024-04-17T18:17:50+08:00",
        keeperName: "MARINA BAY SANDS PTE. LTD.",
        totalRooms: 2561,
        url: "https://www.marinabaysands.com",
        incCrc: "Y",
      },
    ] as never);

    const jsonResult = await handleBusinessDossier({
      entityName: "Marina Bay Sands",
      modules: ["hlb"],
      sectorHints: ["hospitality"],
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect(payload.riskFlags ?? []).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ code: "NO_ACRA_MATCH" })]),
    );
    expect(payload.matchConfidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "HLB hotels", confidence: "name-exact", matchedOn: "name" }),
      ]),
    );
  });

  it("treats Live Company as active and preserves exact UEN match confidence", async () => {
    vi.mocked(getAcraEntities).mockResolvedValue([
      {
        entityName: "ABC CONSTRUCTION PTE LTD",
        uen: "201912345K",
        entityStatusDescription: "Live Company",
      },
    ] as never);
    vi.mocked(getBcaLicensedBuilders).mockResolvedValue([
      {
        uenNo: "201912345K",
        classCode: "GB1",
        expiryDate: "2026-12-31",
      },
    ] as never);
    vi.mocked(getBcaRegisteredContractors).mockResolvedValue([
      {
        uenNo: "201912345K",
        workhead: "CW01",
        expiryDate: "2026-12-31",
      },
    ] as never);

    const jsonResult = await handleBusinessDossier({
      uen: "201912345K",
      modules: ["acra", "bca"],
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect(payload.riskFlags ?? []).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ code: "ENTITY_NOT_ACTIVE" })]),
    );
    expect(payload.matchConfidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "ACRA", confidence: "exact", matchedOn: "uen" }),
        expect.objectContaining({ source: "BCA licensed builders", confidence: "exact", matchedOn: "uenNo" }),
        expect.objectContaining({ source: "BCA registered contractors", confidence: "exact", matchedOn: "uenNo" }),
      ]),
    );
  });

  it("returns the expanded property brief envelope", async () => {
    vi.mocked(lookupPlanningArea).mockResolvedValue([
      { planningArea: "Bedok", region: "East Region" },
    ] as never);
    vi.mocked(getPropertyTransactions).mockResolvedValue([
      { price: "1200000", contractDate: "2026-03" },
    ] as never);
    vi.mocked(getHdbResalePrices).mockResolvedValue([
      { resalePrice: 560000, month: "2026-03" },
    ] as never);
    vi.mocked(getForecast2Hr).mockResolvedValue([
      { area: "Bedok", forecast: "Cloudy", updatedAt: "2026-03-26T08:00:00+08:00" },
    ] as never);
    vi.mocked(getAirQuality).mockResolvedValue([
      { region: "East", psi24h: 42, updatedAt: "2026-03-26T08:00:00+08:00" },
    ] as never);
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [{ line: "EWL" }],
      messages: [{ content: "Delay", createdDate: "2026-03-26T08:00:00+08:00" }],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([
      { type: "Accident" },
    ] as never);

    const jsonResult = await handlePropertyBrief({
      planningArea: "Bedok",
      includeTransport: true,
      includeEnvironment: true,
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect(payload.title).toBe("Property Brief");
    expect(payload.provenance.length).toBeGreaterThanOrEqual(6);
    expect(payload.records["trainAlerts"]).toBeDefined();
    expect(payload.records["locationResolution"]).toMatchObject({
      requestedPlanningArea: "Bedok",
      resolvedPlanningArea: "Bedok",
      resolvedRegion: "East",
    });
    expect((payload.records["confidence"] as Record<string, unknown>)["geospatial"]).toMatchObject({
      level: "medium",
    });
    expect((payload.records["contextSignals"] as Record<string, unknown>)).toMatchObject({
      transport: expect.objectContaining({ tier: "disrupted", trainAlertCount: 1 }),
      environment: expect.objectContaining({ tier: "clear", forecastRisk: "clear", airQualityBand: "clear" }),
    });
    expect(payload.riskFlags).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "MARKET_CONTEXT_DIVERGENCE", source: "URA/HDB" }),
      ]),
    );
    expect(payload.records["provenanceSummary"]).toBeDefined();
    expect(payload.records["freshnessSummary"]).toBeDefined();
    expect(payload.nextChecks).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          tool: "sg_ura_property_transactions",
          input: expect.objectContaining({ area: "Bedok" }),
        }),
      ]),
    );

    const markdownResult = await handlePropertyBrief({
      planningArea: "Bedok",
      includeTransport: true,
      includeEnvironment: true,
      format: "markdown",
    });
    expectMarkdownSections(getText(markdownResult));
  });

  it("flags low geospatial confidence when location resolution fails", async () => {
    vi.mocked(lookupPlanningArea).mockResolvedValue([] as never);

    const jsonResult = await handlePropertyBrief({
      postalCode: "999999",
      includeTransport: false,
      includeEnvironment: false,
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect((payload.records["confidence"] as Record<string, unknown>)["geospatial"]).toMatchObject({
      level: "low",
    });
    expect(payload.riskFlags).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "UNRESOLVED_LOCATION", source: "OneMap" }),
        expect.objectContaining({ code: "LOW_GEOSPATIAL_CONFIDENCE", source: "OneMap/URA" }),
      ]),
    );
  });

  it("returns the expanded macro brief envelope", async () => {
    vi.mocked(fetchNormalizedMasRecords).mockImplementation(async (dataset) => {
      if (dataset === MasDataset.EXCHANGE_RATES) {
        return [
          { date: "2026-03-26", usd_sgd: 1.35 },
          { date: "2026-03-25", usd_sgd: 1.34 },
        ] as never;
      }
      if (dataset === MasDataset.INTEREST_RATES_SORA) {
        return [
          { date: "2026-03-26", preliminary: 0, sora_3m: 3.2 },
          { date: "2026-03-25", preliminary: 0, sora_3m: 3.1 },
        ] as never;
      }
      return [
        { date: "2026-03-26", preliminary: 0, total_deposits: 1000 },
        { date: "2026-03-25", preliminary: 0, total_deposits: 980 },
      ] as never;
    });
    vi.mocked(getSingStatTableData).mockImplementation(async (tableId) => {
      if (tableId === "M015631") {
        return {
          rows: [
            { period: "2025 4Q", variable: "GDP At Current Market Prices", value: 156000, unit: "million dollars" },
            { period: "2025 3Q", variable: "GDP At Current Market Prices", value: 154000, unit: "million dollars" },
          ],
          metadata: {
            title: "Gross Domestic Product",
            frequency: "Quarterly",
            source: "SingStat",
            lastUpdated: "2026-03-01",
          },
          total: 2,
        } as never;
      }
      if (tableId === "M213781") {
        return {
          rows: [
            { period: "2026 Feb", variable: "All Items", value: 1.6, unit: "percent" },
            { period: "2026 Jan", variable: "All Items", value: 1.4, unit: "percent" },
          ],
          metadata: {
            title: "Consumer Price Index - Year on Year",
            frequency: "Monthly",
            source: "SingStat",
            lastUpdated: "2026-03-01",
          },
          total: 2,
        } as never;
      }
      return {
        rows: [
          { period: "2026 Feb", variable: "All Items", value: 116.2, unit: "index" },
          { period: "2026 Jan", variable: "All Items", value: 115.9, unit: "index" },
        ],
        metadata: {
          title: "Consumer Price Index",
          frequency: "Monthly",
          source: "SingStat",
          lastUpdated: "2026-03-01",
        },
        total: 2,
      } as never;
    });

    const jsonResult = await handleMacroBrief({
      currency: "USD",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const summaryByLabel = new Map(payload.summary.map((item) => [item.label, item.value]));
    const evidenceByLabel = new Map(payload.evidence.map((item) => [item.label, item.value]));

    expect(payload.title).toBe("Macro Brief");
    expectBriefQualityContract(payload, {
      title: "Macro Brief",
      requiredRecords: ["kpis", "headlines", "exchangeRates", "gdpSeries", "cpiYoYSeries"],
      requiredTools: ["sg_mas_exchange_rates", "sg_mas_interest_rates", "sg_mas_financial_stats", "sg_singstat_table"],
      requiredLimitCodes: ["STARTER_SNAPSHOT", "BOUNDED_SINGSTAT_SERIES", "NO_FORWARD_VIEW"],
    });
    expect(payload.provenance).toHaveLength(4);
    expect(payload.summary.some((item) => item.label === "GDP table ID")).toBe(true);
    expect(summaryByLabel.get("3M SORA")).toBe(3.2);
    expect(summaryByLabel.get("Total deposits")).toBe(1000);
    expect(summaryByLabel.get("GDP at current prices")).toBe(156000);
    expect(summaryByLabel.get("CPI YoY table ID")).toBe("M213781");
    expect(summaryByLabel.get("CPI index table ID")).toBe("M213751");
    expect(summaryByLabel.get("CPI YoY table ID")).not.toBe(summaryByLabel.get("GDP table ID"));
    expect(evidenceByLabel.get("Primary SORA key")).toBe("sora_3m");
    expect(evidenceByLabel.get("Primary banking key")).toBe("total_deposits");
    expect(evidenceByLabel.get("Primary SORA key")).not.toBe("preliminary");
    expect(evidenceByLabel.get("Primary banking key")).not.toBe("preliminary");
    expect(payload.records["kpis"]).toMatchObject({
      currency: "USD",
      interestRate: { metric: "3M SORA", key: "sora_3m", value: 3.2 },
      banking: { metric: "Total deposits", key: "total_deposits", value: 1000, deltaPercent: 2.04 },
      singstatSeries: {
        gdpTableId: "M015631",
        gdpPeriod: "2025 4Q",
        gdpDeltaPercent: 1.3,
        cpiYoYTableId: "M213781",
        cpiYoYDeltaPercent: expect.any(Number),
        cpiIndexTableId: "M213751",
        cpiIndexDeltaPercent: expect.any(Number),
      },
    });
    expect(payload.records["headlines"]).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "SORA", headline: "3M SORA at 3.2%", source: "MAS" }),
        expect.objectContaining({ code: "GDP", headline: "GDP at current prices at 156000 for 2025 4Q", tableId: "M015631" }),
        expect.objectContaining({ code: "CPI_YOY", headline: "CPI YoY at 1.6% for 2026 Feb", tableId: "M213781" }),
      ]),
    );
    expect(summaryByLabel.get("Banking period delta %")).toBe(2.04);
    expect(summaryByLabel.get("GDP period delta %")).toBe(1.3);
    expect(typeof summaryByLabel.get("CPI YoY period delta %")).toBe("number");
    expect(typeof summaryByLabel.get("CPI index period delta %")).toBe("number");

    const markdownResult = await handleMacroBrief({
      currency: "USD",
      format: "markdown",
    });
    expectMarkdownSections(getText(markdownResult));

    const headlines = payload.records["headlines"] as readonly Record<string, unknown>[];
    const gdpHeadline = headlines.find((h) => h["code"] === "GDP");
    const cpiHeadline = headlines.find((h) => h["code"] === "CPI_YOY");
    const soraHeadline = headlines.find((h) => h["code"] === "SORA");
    const bankingHeadline = headlines.find((h) => h["code"] === "BANKING");

    // CPI/GDP separation: tableIds must not collide and headline strings must not cross-reference each other.
    expect(gdpHeadline?.["tableId"]).toBe("M015631");
    expect(cpiHeadline?.["tableId"]).toBe("M213781");
    expect(gdpHeadline?.["tableId"]).not.toBe(cpiHeadline?.["tableId"]);
    expect(String(gdpHeadline?.["headline"] ?? "")).not.toMatch(/CPI/i);
    expect(String(cpiHeadline?.["headline"] ?? "")).not.toMatch(/GDP/i);

    // SORA / banking labels must be named, not generic placeholder strings.
    expect(String(soraHeadline?.["headline"] ?? "")).not.toMatch(/^SORA metric/);
    expect(String(soraHeadline?.["headline"] ?? "")).not.toMatch(/CPI|GDP/i);
    expect(String(bankingHeadline?.["headline"] ?? "")).not.toMatch(/^MAS banking metric at/);
    expect(String(bankingHeadline?.["headline"] ?? "")).not.toMatch(/CPI|GDP/i);

    // Summary must not contain a generic 'metric' label fallback once SORA / banking are mapped.
    expect(payload.summary.some((item) => item.label === "SORA metric")).toBe(false);
    expect(payload.summary.some((item) => item.label === "MAS Banking metric")).toBe(false);
  });

  it("fails loud with gaps when MAS interest and banking records lack known metric fields", async () => {
    vi.mocked(fetchNormalizedMasRecords).mockImplementation(async (dataset) => {
      if (dataset === MasDataset.EXCHANGE_RATES) {
        return [{ date: "2026-03-26", usd_sgd: 1.35 }] as never;
      }
      if (dataset === MasDataset.INTEREST_RATES_SORA) {
        return [{ date: "2026-03-26", preliminary: 0, unknown_field: 42 }] as never;
      }
      return [{ date: "2026-03-26", preliminary: 0, mystery_metric: 999 }] as never;
    });
    vi.mocked(getSingStatTableData).mockResolvedValue({
      rows: [],
      metadata: { title: "", frequency: "", source: "", lastUpdated: null },
      total: 0,
    } as never);

    const result = await handleMacroBrief({ currency: "USD", format: "json" });
    const payload = parseBrief(getText(result));
    const summaryByLabel = new Map(payload.summary.map((item) => [item.label, item.value]));
    const gapCodes = payload.gaps.map((gap) => gap.code);

    expect(gapCodes).toContain("MAS_SORA_METRIC_UNMAPPED");
    expect(gapCodes).toContain("MAS_BANKING_METRIC_UNMAPPED");
    expect(summaryByLabel.get("SORA")).toBeNull();
    expect(summaryByLabel.get("MAS Banking (unavailable)")).toBeNull();
    expect(payload.summary.some((item) => item.label.toLowerCase().includes("mystery"))).toBe(false);
    expect(payload.summary.some((item) => item.label.toLowerCase().includes("unknown"))).toBe(false);
  });

  it("returns the expanded transport brief envelope", async () => {
    vi.mocked(getBusArrivals).mockResolvedValue([
      {
        busStopCode: "83139",
        serviceNo: "851",
        operator: "SBST",
        arrivals: [{ estimatedArrival: "2099-03-26T08:05:00+08:00" }],
      },
    ] as never);
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [{ line: "NSL" }],
      messages: [{ content: "Minor delay", createdDate: "2026-03-26T08:00:00+08:00" }],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([
      { type: "Road Works" },
    ] as never);

    const jsonResult = await handleTransportBrief({
      busStopCode: "83139",
      serviceNo: "851",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect(payload.title).toBe("Transport Brief");
    expectBriefQualityContract(payload, {
      title: "Transport Brief",
      requiredRecords: ["status", "coverage", "serviceStatusByMode", "signals", "followups", "actionTemplates"],
      requiredTools: ["sg_lta_bus_arrivals", "sg_lta_train_alerts", "sg_lta_traffic_incidents"],
      requiredLimitCodes: ["SNAPSHOT_ONLY", "NO_ROUTE_PLANNING"],
    });
    expect(payload.provenance).toHaveLength(3);
    expect(payload.summary.some((item) => item.label === "Transport status")).toBe(true);
    expect((payload.records["status"] as Record<string, unknown>)["level"]).toBe("disrupted");
    expect((payload.records["status"] as Record<string, unknown>)["escalationTier"]).toBe("tier2_investigate");
    expect((payload.records["status"] as Record<string, unknown>)["signalId"]).toEqual(expect.stringContaining("transport-status:"));
    expect((payload.records["coverage"] as Record<string, unknown>)["train"]).toMatchObject({
      status: "alerts_active",
      alertCount: 1,
      messageCount: 1,
    });
    expect(payload.records["signals"]).toBeDefined();
    expect((payload.records["network"] as Record<string, unknown>)["trainByLine"]).toMatchObject({ NSL: 1 });
    expect(payload.records["followups"]).toBeDefined();
    expect(payload.records["actionTemplates"]).toBeDefined();
    expect((payload.records["signalIds"] as Record<string, unknown>)["signals"]).toEqual(
      expect.arrayContaining([expect.stringContaining("transport-train:")]),
    );
    expect((payload.records["stop"] as Record<string, unknown>)).toMatchObject({
      busStopCode: "83139",
      serviceNo: "851",
      serviceCount: 1,
      nextArrival: "2099-03-26T08:05:00+08:00",
    });
    expect((payload.records["raw"] as Record<string, unknown>)["trainMessages"]).toBeDefined();

    const markdownResult = await handleTransportBrief({
      busStopCode: "83139",
      serviceNo: "851",
      format: "markdown",
    });
    expectMarkdownSections(getText(markdownResult));
  });

  it("returns advisory transport status when only traffic incidents are active", async () => {
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [],
      messages: [],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([
      { type: "Accident" },
    ] as never);

    const jsonResult = await handleTransportBrief({
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const status = payload.records["status"] as Record<string, unknown>;
    const network = payload.records["network"] as Record<string, unknown>;

    expect(status["level"]).toBe("advisory");
    expect(status["focus"]).toBe("network-wide");
    expect(network["trafficByType"]).toMatchObject({ Accident: 1 });
    expect((payload.records["coverage"] as Record<string, unknown>)["traffic"]).toMatchObject({
      status: "incidents_active",
      incidentCount: 1,
    });
  });

  it("returns unknown transport status when a requested bus stop has no ETA and no broader signals", async () => {
    vi.mocked(getBusArrivals).mockResolvedValue([
      {
        busStopCode: "83139",
        serviceNo: "851",
        arrivals: [{ estimatedArrival: null }],
      },
    ] as never);
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [],
      messages: [],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([] as never);

    const jsonResult = await handleTransportBrief({
      busStopCode: "83139",
      serviceNo: "851",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const status = payload.records["status"] as Record<string, unknown>;
    const followups = payload.records["followups"] as readonly Record<string, unknown>[];
    const stop = payload.records["stop"] as Record<string, unknown>;

    expect(status["level"]).toBe("unknown");
    expect(followups.map((check) => check["tool"])).toEqual([
      "sg_lta_bus_arrivals",
      "sg_lta_train_alerts",
      "sg_lta_traffic_incidents",
    ]);
    expect((followups[0]?.["input"] as Record<string, unknown>)["busStopCode"]).toBe("83139");
    expect((followups[0]?.["input"] as Record<string, unknown>)["serviceNo"]).toBe("851");
    expect(stop["nextArrival"]).toBeNull();
  });

  it("returns normal transport status when the requested stop has arrivals and no disruptions", async () => {
    vi.mocked(getBusArrivals).mockResolvedValue([
      {
        busStopCode: "83139",
        serviceNo: "851",
        arrivals: [{ estimatedArrival: "2099-03-26T08:05:00+08:00" }],
      },
    ] as never);
    vi.mocked(getTrainAlerts).mockResolvedValue({
      alerts: [],
      messages: [],
    } as never);
    vi.mocked(getTrafficIncidents).mockResolvedValue([] as never);

    const jsonResult = await handleTransportBrief({
      busStopCode: "83139",
      serviceNo: "851",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const status = payload.records["status"] as Record<string, unknown>;

    expect(status["level"]).toBe("normal");
    expect(status["focus"]).toBe("bus stop 83139 service 851");
    expect((payload.records["stop"] as Record<string, unknown>)["avgWaitMinutes"]).not.toBeNull();
  });

  it("returns the expanded environment brief envelope", async () => {
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Tampines",
        forecast: "Partly Cloudy",
        updatedAt: "2026-03-26T08:00:00+08:00",
        validFrom: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getAirQuality).mockResolvedValue([
      {
        region: "East",
        psi24h: 40,
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getRainfall).mockResolvedValue([
      {
        stationName: "Tampines",
        value: 0.2,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect(payload.title).toBe("Environment Brief");
    expectBriefQualityContract(payload, {
      title: "Environment Brief",
      requiredRecords: ["status", "coverage", "thresholds", "signals", "followups", "actionTemplates"],
      requiredTools: ["sg_nea_forecast_2hr", "sg_nea_air_quality", "sg_nea_rainfall"],
      requiredLimitCodes: ["LIVE_SNAPSHOT_ONLY"],
    });
    expect(payload.provenance).toHaveLength(3);
    expect(payload.summary.some((item) => item.label === "Monitoring status")).toBe(true);
    expect((payload.records["status"] as Record<string, unknown>)["level"]).toBe("watch");
    expect((payload.records["status"] as Record<string, unknown>)["escalationTier"]).toBe("tier1_notify");
    expect((payload.records["status"] as Record<string, unknown>)["signalId"]).toEqual(expect.stringContaining("environment-status:"));
    expect((payload.records["coverage"] as Record<string, unknown>)["forecast"]).toMatchObject({
      status: "available",
      requestedArea: "Tampines",
      resolvedArea: "Tampines",
    });
    expect(payload.records["thresholds"]).toBeDefined();
    expect(payload.records["signals"]).toBeDefined();
    expect((payload.records["focus"] as Record<string, unknown>)).toMatchObject({
      area: "Tampines",
      region: "East",
      stationName: "Tampines",
    });
    expect(payload.records["followups"]).toBeDefined();
    expect(payload.records["actionTemplates"]).toBeDefined();
    expect((payload.records["signalIds"] as Record<string, unknown>)["signals"]).toEqual(
      expect.arrayContaining([expect.stringContaining("environment-forecast:")]),
    );
    expect((payload.records["raw"] as Record<string, unknown>)["forecastRows"]).toBeDefined();

    const markdownResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "markdown",
    });
    expectMarkdownSections(getText(markdownResult));
  });

  it("returns caution environment status for thundery or heavy-rain forecasts", async () => {
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Tampines",
        forecast: "Thundery Showers",
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getAirQuality).mockResolvedValue([
      {
        region: "East",
        psi24h: 40,
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getRainfall).mockResolvedValue([
      {
        stationId: "S107",
        stationName: "Tampines",
        value: 0,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect((payload.records["status"] as Record<string, unknown>)["level"]).toBe("caution");
    expect((payload.records["thresholds"] as Record<string, unknown>)["forecastRisk"]).toBe("caution");
    expect((payload.records["thresholds"] as Record<string, unknown>)["advisory"]).toBe("Avoid prolonged outdoor activities");
  });

  it("returns watch environment status for moderate PSI with no rain", async () => {
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Tampines",
        forecast: "Partly Cloudy",
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getAirQuality).mockResolvedValue([
      {
        region: "East",
        psi24h: 75,
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getRainfall).mockResolvedValue([
      {
        stationId: "S107",
        stationName: "Tampines",
        value: 0,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));
    const followups = payload.records["followups"] as readonly Record<string, unknown>[];

    expect((payload.records["status"] as Record<string, unknown>)["level"]).toBe("watch");
    expect((payload.records["thresholds"] as Record<string, unknown>)["airQualityBand"]).toBe("watch");
    expect((followups[0]?.["input"] as Record<string, unknown>)["area"]).toBe("Tampines");
    expect((followups[1]?.["input"] as Record<string, unknown>)["region"]).toBe("East");
    expect((followups[2]?.["input"] as Record<string, unknown>)["stationId"]).toBe("S107");
  });

  it("returns clear environment status when forecast, air quality, and rainfall are all clear", async () => {
    vi.mocked(getForecast2Hr).mockResolvedValue([
      {
        area: "Tampines",
        forecast: "Partly Cloudy",
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getAirQuality).mockResolvedValue([
      {
        region: "East",
        psi24h: 40,
        updatedAt: "2026-03-26T08:00:00+08:00",
      },
    ] as never);
    vi.mocked(getRainfall).mockResolvedValue([
      {
        stationId: "S107",
        stationName: "Tampines",
        value: 0,
        timestamp: "2026-03-26T08:00:00+08:00",
      },
    ] as never);

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect((payload.records["status"] as Record<string, unknown>)["level"]).toBe("clear");
    expect((payload.records["thresholds"] as Record<string, unknown>)["rainfallBand"]).toBe("clear");
  });

  it("returns unknown environment status when all upstream reads fail", async () => {
    vi.mocked(getForecast2Hr).mockRejectedValue(new Error("forecast unavailable"));
    vi.mocked(getAirQuality).mockRejectedValue(new Error("air unavailable"));
    vi.mocked(getRainfall).mockRejectedValue(new Error("rainfall unavailable"));

    const jsonResult = await handleEnvironmentBrief({
      area: "Tampines",
      region: "East",
      stationId: "S107",
      format: "json",
    });
    const payload = parseBrief(getText(jsonResult));

    expect((payload.records["status"] as Record<string, unknown>)["level"]).toBe("unknown");
    expect(payload.gaps).toHaveLength(3);
    expect(payload.records["signals"]).toEqual([]);
    expect((payload.records["raw"] as Record<string, unknown>)).toEqual({
      forecastRows: [],
      airQualityRows: [],
      rainfallRows: [],
    });
  });
});
