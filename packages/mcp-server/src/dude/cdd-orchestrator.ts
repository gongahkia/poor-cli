import { getPeopleDiscovery, getWebPresence, type PeopleDiscovery, type WebPresence } from "../apis/tinyfish/client.js";
import type { BusinessDossierModule, BusinessSectorHint } from "../diligence/entity-resolution.js";
import { generateAnalystMemo, type AnalystMemoDossier } from "./analyst-memo.js";
import { handleBusinessDossier } from "../tools/brief-tools.js";

type BusinessDossierInput = Parameters<typeof handleBusinessDossier>[0];
type AnalystMemoResponse = Awaited<ReturnType<typeof generateAnalystMemo>>;

export type CddOrchestratorResponse = {
  readonly dossier: AnalystMemoDossier;
  readonly webPresence: WebPresence;
  readonly peopleDiscovery: PeopleDiscovery;
  readonly memo: AnalystMemoResponse;
  readonly generatedAt: string;
  readonly orchestration: {
    readonly status: "ready" | "identity_not_resolved";
    readonly strategy: "acra_then_sector_then_supplemental_memo";
    readonly acraSectorHints: readonly BusinessSectorHint[];
    readonly webSectorHints: readonly BusinessSectorHint[];
    readonly effectiveSectorHints: readonly BusinessSectorHint[];
    readonly officialModules: readonly string[];
    readonly supplementalTools: readonly string[];
    readonly reranDossierForWebSectorHints: boolean;
    readonly limits: readonly string[];
  };
};

export class CddOrchestratorBadRequestError extends Error {
  readonly statusCode = 400;

  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "CddOrchestratorBadRequestError";
  }
}

const UEN_PATTERN = /^(?:\d{8,9}[a-z]|[a-z]\d{2}[a-z]{2}\d{4}[a-z])$/i;

const BUSINESS_DOSSIER_MODULES = [
  "acra",
  "bca",
  "cea",
  "gebiz",
  "boa",
  "hsa",
  "hlb",
] as const satisfies readonly BusinessDossierModule[];

const BUSINESS_SECTOR_HINTS = [
  "construction",
  "real_estate",
  "architecture",
  "healthcare",
  "hospitality",
  "procurement",
] as const satisfies readonly BusinessSectorHint[];

const CDD_ORCHESTRATOR_SUPPLEMENTAL_TOOLS = [
  "sg_sanctions_screen",
  "sg_opencorporates_links",
  "sg_adverse_media_lite",
  "sg_relationship_graph",
] as const;

const BUSINESS_IDENTIFIER_FIELDS = [
  "entityName",
  "uen",
  "salespersonName",
  "registrationNo",
  "estateAgentName",
  "estateAgentLicenseNo",
  "classCode",
  "workhead",
  "grade",
] as const;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const isDossier = (value: unknown): value is AnalystMemoDossier =>
  isRecord(value)
  && typeof value["title"] === "string"
  && Array.isArray(value["summary"])
  && Array.isArray(value["evidence"])
  && isRecord(value["records"])
  && Array.isArray(value["gaps"])
  && Array.isArray(value["provenance"])
  && Array.isArray(value["freshness"])
  && Array.isArray(value["limits"]);

const isBusinessDossierModule = (value: unknown): value is BusinessDossierModule =>
  typeof value === "string" && (BUSINESS_DOSSIER_MODULES as readonly string[]).includes(value);

const isBusinessSectorHint = (value: unknown): value is BusinessSectorHint =>
  typeof value === "string" && (BUSINESS_SECTOR_HINTS as readonly string[]).includes(value);

const buildBusinessDossierInputFromIdentifier = (identifier: string): { readonly uen: string } | { readonly entityName: string } =>
  UEN_PATTERN.test(identifier)
    ? { uen: identifier.toUpperCase() }
    : { entityName: identifier };

const getOptionalString = (record: Record<string, unknown>, field: string): string | null => {
  const value = record[field];
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
};

const getStringArray = <T extends string>(
  value: unknown,
  guard: (candidate: unknown) => candidate is T,
): readonly T[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  const values = new Set<T>();
  for (const candidate of value) {
    if (guard(candidate)) {
      values.add(candidate);
    }
  }
  return Array.from(values);
};

export const normalizeCddOrchestratorInput = (input: Record<string, unknown>): BusinessDossierInput => {
  const identifier = getOptionalString(input, "identifier");
  const output: Record<string, unknown> = identifier === null
    ? {}
    : { ...buildBusinessDossierInputFromIdentifier(identifier) };

  for (const field of BUSINESS_IDENTIFIER_FIELDS) {
    const value = getOptionalString(input, field);
    if (value !== null) {
      output[field] = field === "uen" ? value.toUpperCase() : value;
    }
  }

  const modules = getStringArray(input["modules"], isBusinessDossierModule);
  if (modules.length > 0) {
    output["modules"] = modules;
  }

  const sectorHints = getStringArray(input["sectorHints"], isBusinessSectorHint);
  if (sectorHints.length > 0) {
    output["sectorHints"] = sectorHints;
  }

  output["includeExternalDiligence"] = true;

  const hasIdentifier = BUSINESS_IDENTIFIER_FIELDS.some((field) => typeof output[field] === "string");
  if (!hasIdentifier) {
    throw new CddOrchestratorBadRequestError(
      "CDD_ORCHESTRATOR_IDENTIFIER_REQUIRED",
      "Provide a Singapore company name, UEN, or supported sector identifier.",
    );
  }

  return output as BusinessDossierInput;
};

const getDossierSummaryString = (
  dossier: AnalystMemoDossier,
  label: string,
): string | null => {
  const match = dossier.summary.find((item) => item.label.toLowerCase() === label.toLowerCase());
  if (match === undefined || match.value === null || match.value === undefined) {
    return null;
  }
  return typeof match.value === "string" ? match.value.trim() || null : String(match.value);
};

const getDossierRecordArray = (
  dossier: AnalystMemoDossier,
  key: string,
): readonly Record<string, unknown>[] => {
  const value = dossier.records[key];
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => isRecord(item))
    : [];
};

const getResolutionStringArray = (
  dossier: AnalystMemoDossier,
  key: string,
): readonly string[] => {
  const resolution = dossier.records["resolution"];
  if (!isRecord(resolution)) {
    return [];
  }
  const value = resolution[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim() !== "").map((item) => item.trim())
    : [];
};

const getResolutionSectorHints = (
  dossier: AnalystMemoDossier,
  key: string,
): readonly BusinessSectorHint[] =>
  getResolutionStringArray(dossier, key).filter(isBusinessSectorHint);

const uniqueSectorHints = (
  hints: readonly (BusinessSectorHint | string)[],
): readonly BusinessSectorHint[] => {
  const unique = new Set<BusinessSectorHint>();
  for (const hint of hints) {
    if (isBusinessSectorHint(hint)) {
      unique.add(hint);
    }
  }
  return Array.from(unique);
};

const normalizeSectorSignalText = (value: string): string =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const inferSectorHintsFromWebPresence = (
  webPresence: WebPresence,
): readonly BusinessSectorHint[] => {
  const text = normalizeSectorSignalText([
    webPresence.possibleOfficialWebsite,
    ...webPresence.results.flatMap((result) => [
      result.title,
      result.snippet,
      result.url,
      result.siteName,
    ]),
  ].filter((part): part is string => typeof part === "string" && part.trim() !== "").join(" "));
  const hints = new Set<BusinessSectorHint>();

  if (/\b(construction|building contractor|civil engineering|licensed builder|registered contractor|bca)\b/.test(text)) {
    hints.add("construction");
  }
  if (/\b(architect|architecture|architectural|boa)\b/.test(text)) {
    hints.add("architecture");
  }
  if (/\b(real estate|estate agent|property agency|salesperson|realtor|cea)\b/.test(text)) {
    hints.add("real_estate");
  }
  if (/\b(healthcare|medical|clinic|hospital|pharma|pharmaceutical|pharmacy|health product|therapeutic|hsa)\b/.test(text)) {
    hints.add("healthcare");
  }
  if (/\b(hotel|hospitality|lodging|serviced apartment|guest room|hlb)\b/.test(text)) {
    hints.add("hospitality");
  }
  if (/\b(gebiz|tender|procurement|government supplier|award notice|quotation)\b/.test(text)) {
    hints.add("procurement");
  }

  return Array.from(hints);
};

const buildWebPresenceQuery = (
  dossier: AnalystMemoDossier,
  input: BusinessDossierInput,
): string => [
  getDossierSummaryString(dossier, "Entity") ?? input.entityName,
  getDossierSummaryString(dossier, "UEN") ?? input.uen,
].filter((part): part is string => typeof part === "string" && part.trim() !== "").join(" ").trim();

const buildSkippedWebPresence = (
  query: string,
  reason: string,
): WebPresence => ({
  query,
  configured: false,
  results: [],
  possibleOfficialWebsite: null,
  limits: [
    reason,
    "Web discovery was not used because the orchestrator stopped before supplemental evidence collection.",
  ],
});

const buildSkippedPeopleDiscovery = (
  params: Readonly<{
    entityName: string;
    uen: string | null;
    reason: string;
  }>,
): PeopleDiscovery => ({
  entityName: params.entityName,
  uen: params.uen,
  query: params.entityName,
  configured: false,
  results: [],
  suggestedActions: [],
  limits: [
    params.reason,
    "People discovery was not used because the orchestrator stopped before supplemental evidence collection.",
  ],
});

const resolveBusinessDossierRecord = async (
  input: BusinessDossierInput,
): Promise<AnalystMemoDossier> => {
  const result = await handleBusinessDossier(input);
  const record = result.structuredContent?.["record"];
  if (!isDossier(record)) {
    throw new CddOrchestratorBadRequestError(
      "CDD_ORCHESTRATOR_DOSSIER_FAILED",
      "Unable to resolve a business dossier for CDD orchestration.",
    );
  }
  return record;
};

export const runCddOrchestrator = async (
  input: BusinessDossierInput,
): Promise<CddOrchestratorResponse> => {
  const generatedAt = new Date().toISOString();
  const baseInput: BusinessDossierInput = {
    ...input,
    includeExternalDiligence: true,
  };
  const firstDossier = await resolveBusinessDossierRecord(baseInput);
  const webPresenceQuery = buildWebPresenceQuery(firstDossier, baseInput);
  const entityName = getDossierSummaryString(firstDossier, "Entity") ?? baseInput.entityName ?? webPresenceQuery;
  const uen = getDossierSummaryString(firstDossier, "UEN") ?? baseInput.uen ?? null;
  const acraRecords = getDossierRecordArray(firstDossier, "acra");
  const acraSectorHints = getResolutionSectorHints(firstDossier, "effectiveSectorHints");

  if (acraRecords.length === 0) {
    const reason = "ACRA did not return a canonical entity record, so automated sector, web, people, and memo orchestration stopped at the identity check.";
    const memo = await generateAnalystMemo({ dossier: firstDossier });
    return {
      dossier: firstDossier,
      webPresence: buildSkippedWebPresence(webPresenceQuery, reason),
      peopleDiscovery: buildSkippedPeopleDiscovery({ entityName, uen, reason }),
      memo,
      generatedAt,
      orchestration: {
        status: "identity_not_resolved",
        strategy: "acra_then_sector_then_supplemental_memo",
        acraSectorHints,
        webSectorHints: [],
        effectiveSectorHints: acraSectorHints,
        officialModules: getResolutionStringArray(firstDossier, "selectedModules"),
        supplementalTools: CDD_ORCHESTRATOR_SUPPLEMENTAL_TOOLS,
        reranDossierForWebSectorHints: false,
        limits: [
          reason,
          "No downstream sector module can be treated as matching the entity until ACRA identity is resolved.",
        ],
      },
    };
  }

  const webPresence = await getWebPresence(webPresenceQuery);
  const webSectorHints = inferSectorHintsFromWebPresence(webPresence);
  const mergedSectorHints = uniqueSectorHints([
    ...getResolutionSectorHints(firstDossier, "sectorHints"),
    ...acraSectorHints,
    ...webSectorHints,
  ]);
  const hasNewWebSectorHint = webSectorHints.some((hint) => !acraSectorHints.includes(hint));
  const finalDossier = hasNewWebSectorHint
    ? await resolveBusinessDossierRecord({
        ...baseInput,
        sectorHints: mergedSectorHints,
      })
    : firstDossier;
  const finalEntityName = getDossierSummaryString(finalDossier, "Entity") ?? entityName;
  const finalUen = getDossierSummaryString(finalDossier, "UEN") ?? uen;
  const peopleDiscovery = await getPeopleDiscovery({
    entityName: finalEntityName,
    ...(finalUen === null ? {} : { uen: finalUen }),
  });
  const memo = await generateAnalystMemo({
    dossier: finalDossier,
    webPresence,
  });

  return {
    dossier: finalDossier,
    webPresence,
    peopleDiscovery,
    memo,
    generatedAt,
    orchestration: {
      status: "ready",
      strategy: "acra_then_sector_then_supplemental_memo",
      acraSectorHints,
      webSectorHints,
      effectiveSectorHints: getResolutionSectorHints(finalDossier, "effectiveSectorHints"),
      officialModules: getResolutionStringArray(finalDossier, "selectedModules"),
      supplementalTools: CDD_ORCHESTRATOR_SUPPLEMENTAL_TOOLS,
      reranDossierForWebSectorHints: hasNewWebSectorHint,
      limits: [
        "ACRA remains the identity gate; TinyFish web signals only add bounded sector hints.",
        "Supplemental sanctions, OpenCorporates, adverse-media, relationship graph, web presence, and people discovery outputs are analyst-review evidence.",
        "Claims remain evidence-bound and should not be treated as legal, AML, sanctions, credit, tax, or investment advice.",
      ],
    },
  };
};
