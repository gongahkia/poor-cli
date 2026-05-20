import { getAcraEntities } from "../apis/acra/client.js";
import { getBcaLicensedBuilders, getBcaRegisteredContractors } from "../apis/bca/client.js";
import { getBoaArchitects, getBoaArchitectureFirms } from "../apis/boa/client.js";
import { getCeaSalespersons } from "../apis/cea/client.js";
import { getGeBIZTenders } from "../apis/gebiz/client.js";
import { getHlbHotels } from "../apis/hlb/client.js";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../apis/hsa/client.js";
import {
  ALL_BUSINESS_DOSSIER_MODULES,
  getBusinessModulesForSector,
  type BusinessDossierModule,
  type BusinessSectorHint,
} from "../diligence/entity-resolution.js";
import {
  normalizeBusinessNameForMatch,
  normalizeBusinessNameForSearch,
  scoreBusinessNameMatch,
  type BusinessNameMatchMethod,
} from "../diligence/name-matching.js";

export type CounterpartyResolverInput = {
  readonly identifier: string;
  readonly modules?: readonly BusinessDossierModule[];
  readonly sectorHints?: readonly BusinessSectorHint[];
  readonly limit?: number;
};

export type CounterpartyResolutionCandidate = {
  readonly id: string;
  readonly label: string;
  readonly sourceRegistry: "ACRA" | "BCA" | "BOA" | "CEA" | "GeBIZ" | "HSA" | "HLB";
  readonly sourceTool: string;
  readonly entityName: string;
  readonly uen: string | null;
  readonly officialIdentifier: string | null;
  readonly description: string;
  readonly score: number;
  readonly matchMethod: BusinessNameMatchMethod | "exact_identifier";
  readonly matchReason: string;
  readonly normalizedName: string;
  readonly dossierInput: Readonly<Record<string, string>>;
};

export type CounterpartyResolutionResult = {
  readonly status: "resolved" | "needs_confirmation" | "no_match";
  readonly originalInput: string;
  readonly normalizedInput: string;
  readonly selectedCandidate: CounterpartyResolutionCandidate | null;
  readonly candidates: readonly CounterpartyResolutionCandidate[];
  readonly confidenceBlockers: readonly string[];
  readonly sourcesSearched: readonly string[];
  readonly limits: readonly string[];
};

const UEN_PATTERN = /^(?:\d{8,9}[a-z]|[a-z]\d{2}[a-z]{2}\d{4}[a-z])$/i;
const DEFAULT_LIMIT = 8;
const AUTO_RESOLVE_SCORE = 0.88;
const AMBIGUITY_SCORE_BAND = 0.05;

const normalizeLimit = (limit: number | undefined): number =>
  Math.min(Math.max(Number.isInteger(limit) ? limit! : DEFAULT_LIMIT, 1), 20);

const isLikelyUen = (value: string): boolean => UEN_PATTERN.test(value.trim());

const selectedModulesForResolution = (
  modules: readonly BusinessDossierModule[] | undefined,
  sectorHints: readonly BusinessSectorHint[] | undefined,
): readonly BusinessDossierModule[] => {
  const selected = new Set<BusinessDossierModule>(modules ?? ALL_BUSINESS_DOSSIER_MODULES);
  for (const sectorHint of sectorHints ?? []) {
    for (const module of getBusinessModulesForSector(sectorHint)) {
      selected.add(module);
    }
  }
  return Array.from(selected);
};

const candidatePriority = (candidate: Pick<CounterpartyResolutionCandidate, "sourceRegistry" | "uen">): number => {
  if (candidate.sourceRegistry === "ACRA") return 10;
  if (candidate.uen !== null) return 8;
  if (candidate.sourceRegistry === "BCA") return 7;
  if (candidate.sourceRegistry === "HSA") return 6;
  if (candidate.sourceRegistry === "BOA") return 5;
  if (candidate.sourceRegistry === "HLB") return 4;
  if (candidate.sourceRegistry === "CEA") return 3;
  return 2;
};

const candidateIdentityKey = (candidate: CounterpartyResolutionCandidate): string =>
  candidate.uen ?? normalizeBusinessNameForMatch(candidate.entityName) ?? candidate.id;

const candidateSort = (
  left: CounterpartyResolutionCandidate,
  right: CounterpartyResolutionCandidate,
): number => {
  const scoreDelta = right.score - left.score;
  if (scoreDelta !== 0) return scoreDelta;
  const priorityDelta = candidatePriority(right) - candidatePriority(left);
  if (priorityDelta !== 0) return priorityDelta;
  return left.label.localeCompare(right.label);
};

const toCandidate = (params: {
  readonly identifier: string;
  readonly sourceRegistry: CounterpartyResolutionCandidate["sourceRegistry"];
  readonly sourceTool: string;
  readonly entityName: string;
  readonly uen?: string | null;
  readonly officialIdentifier?: string | null;
  readonly description: string;
  readonly dossierInput?: Readonly<Record<string, string>>;
}): CounterpartyResolutionCandidate | null => {
  const nameScore = scoreBusinessNameMatch(params.identifier, params.entityName);
  const exactIdentifier = params.uen !== undefined
    && params.uen !== null
    && params.uen.toUpperCase() === params.identifier.trim().toUpperCase();
  if (!exactIdentifier && !nameScore.matches) {
    return null;
  }

  const uen = params.uen ?? null;
  const officialIdentifier = params.officialIdentifier ?? null;
  return {
    id: [
      params.sourceTool,
      uen,
      officialIdentifier,
      normalizeBusinessNameForMatch(params.entityName),
    ].filter((part): part is string => typeof part === "string" && part !== "").join(":"),
    label: params.entityName,
    sourceRegistry: params.sourceRegistry,
    sourceTool: params.sourceTool,
    entityName: params.entityName,
    uen,
    officialIdentifier,
    description: params.description,
    score: exactIdentifier ? 1 : nameScore.score,
    matchMethod: exactIdentifier ? "exact_identifier" : nameScore.method,
    matchReason: exactIdentifier ? "Exact UEN match." : nameScore.reason,
    normalizedName: normalizeBusinessNameForMatch(params.entityName),
    dossierInput: params.dossierInput ?? (uen === null ? { entityName: params.entityName } : { uen }),
  };
};

const safeRead = async <T>(read: () => Promise<T>): Promise<T | null> => {
  try {
    return await read();
  } catch {
    return null;
  }
};

const dedupeCandidates = (
  candidates: readonly CounterpartyResolutionCandidate[],
): readonly CounterpartyResolutionCandidate[] => {
  const byKey = new Map<string, CounterpartyResolutionCandidate>();
  for (const candidate of [...candidates].sort(candidateSort)) {
    const key = candidateIdentityKey(candidate);
    const existing = byKey.get(key);
    if (existing === undefined || candidateSort(candidate, existing) < 0) {
      byKey.set(key, candidate);
    }
  }
  return Array.from(byKey.values()).sort(candidateSort);
};

const resolveStatus = (
  candidates: readonly CounterpartyResolutionCandidate[],
): Pick<CounterpartyResolutionResult, "status" | "selectedCandidate" | "confidenceBlockers"> => {
  const top = candidates[0];
  if (top === undefined) {
    return {
      status: "no_match",
      selectedCandidate: null,
      confidenceBlockers: ["No retained CDD registry returned a bounded match for the input."],
    };
  }

  const ambiguousPeers = candidates.filter((candidate) =>
    candidate.score >= AUTO_RESOLVE_SCORE
    && candidate.score >= top.score - AMBIGUITY_SCORE_BAND,
  );
  const peerIdentityKeys = new Set(ambiguousPeers.map(candidateIdentityKey));
  if (top.score >= AUTO_RESOLVE_SCORE && peerIdentityKeys.size <= 1) {
    return {
      status: "resolved",
      selectedCandidate: top,
      confidenceBlockers: top.matchMethod === "typo"
        ? ["The selected candidate relied on bounded typo matching; verify source rows before final decisions."]
        : [],
    };
  }

  return {
    status: "needs_confirmation",
    selectedCandidate: null,
    confidenceBlockers: [
      ambiguousPeers.length > 1
        ? "Multiple official registry candidates are plausible; analyst confirmation is required before running CDD."
        : "The strongest registry candidate is below the automatic resolution threshold.",
    ],
  };
};

export const buildDossierInputFromResolutionCandidate = (
  candidate: CounterpartyResolutionCandidate,
): Readonly<Record<string, string>> => candidate.dossierInput;

export const isResolutionCandidate = (value: unknown): value is CounterpartyResolutionCandidate => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return typeof record["id"] === "string"
    && typeof record["label"] === "string"
    && typeof record["entityName"] === "string"
    && typeof record["sourceTool"] === "string"
    && typeof record["score"] === "number";
};

export const buildConfirmedResolution = (
  originalInput: string,
  candidate: CounterpartyResolutionCandidate,
): CounterpartyResolutionResult => ({
  status: "resolved",
  originalInput,
  normalizedInput: normalizeBusinessNameForSearch(originalInput),
  selectedCandidate: candidate,
  candidates: [candidate],
  confidenceBlockers: candidate.matchMethod === "typo"
    ? ["The confirmed candidate relied on bounded typo matching; verify source rows before final decisions."]
    : [],
  sourcesSearched: [candidate.sourceRegistry],
  limits: [
    "Candidate was explicitly confirmed by the caller before CDD orchestration.",
    "Official identifiers are exact-match only and are never fuzzy-matched.",
  ],
});

export const resolveCounterparty = async (
  input: CounterpartyResolverInput,
): Promise<CounterpartyResolutionResult> => {
  const identifier = input.identifier.trim();
  const limit = normalizeLimit(input.limit);
  const normalizedInput = normalizeBusinessNameForSearch(identifier);
  const modules = selectedModulesForResolution(input.modules, input.sectorHints);
  const sourcesSearched = new Set<string>(["ACRA"]);
  const candidates: CounterpartyResolutionCandidate[] = [];

  if (identifier === "") {
    return {
      status: "no_match",
      originalInput: input.identifier,
      normalizedInput,
      selectedCandidate: null,
      candidates: [],
      confidenceBlockers: ["No counterparty identifier was supplied."],
      sourcesSearched: [],
      limits: ["Resolver only accepts a company name, UEN, or retained CDD registry name identifier."],
    };
  }

  if (isLikelyUen(identifier)) {
    const acra = await safeRead(() => getAcraEntities({ uen: identifier, limit: 1 }));
    const candidate = acra?.[0] === undefined ? null : toCandidate({
      identifier,
      sourceRegistry: "ACRA",
      sourceTool: "sg_acra_entities",
      entityName: acra[0].entityName,
      uen: acra[0].uen,
      officialIdentifier: acra[0].uen,
      description: `${acra[0].uen} - ${acra[0].entityStatusDescription} - ${acra[0].entityTypeDescription}`,
      dossierInput: { uen: acra[0].uen },
    });
    const exactCandidates = candidate === null ? [] : [candidate];
    return {
      ...resolveStatus(exactCandidates),
      originalInput: input.identifier,
      normalizedInput,
      candidates: exactCandidates,
      sourcesSearched: ["ACRA"],
      limits: ["UEN-like inputs are matched exactly; Dude does not fuzzy-match official identifiers."],
    };
  }

  const acra = await safeRead(() => getAcraEntities({ entityName: identifier, limit }));
  for (const record of acra ?? []) {
    const candidate = toCandidate({
      identifier,
      sourceRegistry: "ACRA",
      sourceTool: "sg_acra_entities",
      entityName: record.entityName,
      uen: record.uen,
      officialIdentifier: record.uen,
      description: `${record.uen} - ${record.entityStatusDescription} - ${record.entityTypeDescription}`,
      dossierInput: { uen: record.uen },
    });
    if (candidate !== null) candidates.push(candidate);
  }

  if (modules.includes("bca")) {
    sourcesSearched.add("BCA");
    const [builders, contractors] = await Promise.all([
      safeRead(() => getBcaLicensedBuilders({ companyName: identifier, limit })),
      safeRead(() => getBcaRegisteredContractors({ companyName: identifier, limit })),
    ]);
    for (const record of builders ?? []) {
      const candidate = toCandidate({
        identifier,
        sourceRegistry: "BCA",
        sourceTool: "sg_bca_licensed_builders",
        entityName: record.companyName,
        uen: record.uenNo,
        officialIdentifier: record.uenNo,
        description: `${record.uenNo} - licensed builder ${record.classCode}`,
        dossierInput: { uen: record.uenNo },
      });
      if (candidate !== null) candidates.push(candidate);
    }
    for (const record of contractors ?? []) {
      const candidate = toCandidate({
        identifier,
        sourceRegistry: "BCA",
        sourceTool: "sg_bca_registered_contractors",
        entityName: record.companyName,
        uen: record.uenNo,
        officialIdentifier: record.uenNo,
        description: `${record.uenNo} - registered contractor ${record.workhead}`,
        dossierInput: { uen: record.uenNo },
      });
      if (candidate !== null) candidates.push(candidate);
    }
  }

  if (modules.includes("cea")) {
    sourcesSearched.add("CEA");
    const [salespeople, estateAgents] = await Promise.all([
      safeRead(() => getCeaSalespersons({ salespersonName: identifier, limit })),
      safeRead(() => getCeaSalespersons({ estateAgentName: identifier, limit })),
    ]);
    for (const record of [...(salespeople ?? []), ...(estateAgents ?? [])]) {
      const entityName = record.estateAgentName || record.salespersonName;
      const candidate = toCandidate({
        identifier,
        sourceRegistry: "CEA",
        sourceTool: "sg_cea_salespersons",
        entityName,
        uen: null,
        officialIdentifier: record.estateAgentLicenseNo || record.registrationNo,
        description: `${record.estateAgentLicenseNo} - ${record.registrationNo}`,
        dossierInput: record.estateAgentName === entityName
          ? { estateAgentName: entityName }
          : { salespersonName: record.salespersonName },
      });
      if (candidate !== null) candidates.push(candidate);
    }
  }

  if (modules.includes("gebiz")) {
    sourcesSearched.add("GeBIZ");
    const tenders = await safeRead(() => getGeBIZTenders({ supplierName: identifier, limit }));
    for (const record of tenders ?? []) {
      const candidate = toCandidate({
        identifier,
        sourceRegistry: "GeBIZ",
        sourceTool: "sg_gebiz_tenders",
        entityName: record.supplierName,
        uen: null,
        officialIdentifier: record.tenderNo,
        description: `${record.tenderNo} - ${record.awardDate}`,
        dossierInput: { entityName: record.supplierName },
      });
      if (candidate !== null) candidates.push(candidate);
    }
  }

  if (modules.includes("boa")) {
    sourcesSearched.add("BOA");
    const [architects, firms] = await Promise.all([
      safeRead(async () => [
        ...await getBoaArchitects({ name: identifier, limit }),
        ...await getBoaArchitects({ firmName: identifier, limit }),
      ]),
      safeRead(() => getBoaArchitectureFirms({ firmName: identifier, limit })),
    ]);
    for (const record of architects ?? []) {
      const entityName = record.firmName ?? record.architectName;
      const candidate = toCandidate({
        identifier,
        sourceRegistry: "BOA",
        sourceTool: "sg_boa_architects",
        entityName,
        uen: null,
        officialIdentifier: record.registrationNo,
        description: `Architect registration ${record.registrationNo}`,
        dossierInput: record.firmName === null ? { entityName } : { entityName: record.firmName },
      });
      if (candidate !== null) candidates.push(candidate);
    }
    for (const record of firms ?? []) {
      const candidate = toCandidate({
        identifier,
        sourceRegistry: "BOA",
        sourceTool: "sg_boa_architecture_firms",
        entityName: record.firmName,
        uen: null,
        officialIdentifier: record.firmEmail,
        description: record.firmAddress ?? "BOA architecture firm",
        dossierInput: { entityName: record.firmName },
      });
      if (candidate !== null) candidates.push(candidate);
    }
  }

  if (modules.includes("hsa")) {
    sourcesSearched.add("HSA");
    const [pharmacies, licensees] = await Promise.all([
      safeRead(() => getHsaLicensedPharmacies({ pharmacyName: identifier, limit })),
      safeRead(() => getHsaHealthProductLicensees({ companyName: identifier, limit })),
    ]);
    for (const record of pharmacies ?? []) {
      const candidate = toCandidate({
        identifier,
        sourceRegistry: "HSA",
        sourceTool: "sg_hsa_licensed_pharmacies",
        entityName: record.pharmacyName,
        uen: null,
        officialIdentifier: record.postalCode,
        description: record.pharmacyAddress,
        dossierInput: { entityName: record.pharmacyName },
      });
      if (candidate !== null) candidates.push(candidate);
    }
    for (const record of licensees ?? []) {
      const candidate = toCandidate({
        identifier,
        sourceRegistry: "HSA",
        sourceTool: "sg_hsa_health_product_licensees",
        entityName: record.companyName,
        uen: null,
        officialIdentifier: record.licenseType,
        description: `${record.licenseType} - ${record.expiryDate ?? "no expiry date"}`,
        dossierInput: { entityName: record.companyName },
      });
      if (candidate !== null) candidates.push(candidate);
    }
  }

  if (modules.includes("hlb")) {
    sourcesSearched.add("HLB");
    const hotels = await safeRead(async () => [
      ...await getHlbHotels({ keeperName: identifier, limit }),
      ...await getHlbHotels({ name: identifier, limit }),
    ]);
    for (const record of hotels ?? []) {
      const entityName = record.keeperName ?? record.name;
      const candidate = toCandidate({
        identifier,
        sourceRegistry: "HLB",
        sourceTool: "sg_hlb_hotels",
        entityName,
        uen: null,
        officialIdentifier: record.postalCode,
        description: `${record.name} - ${record.address}`,
        dossierInput: { entityName },
      });
      if (candidate !== null) candidates.push(candidate);
    }
  }

  const rankedCandidates = dedupeCandidates(candidates).slice(0, limit);
  return {
    ...resolveStatus(rankedCandidates),
    originalInput: input.identifier,
    normalizedInput,
    candidates: rankedCandidates,
    sourcesSearched: Array.from(sourcesSearched),
    limits: [
      "Resolver ranks official registry candidates only; it does not infer clearance or risk posture.",
      "Official identifiers are exact-match only and are never fuzzy-matched.",
      "Name fuzzy matching is bounded to aliases, legal suffix normalization, token overlap, and small typo distance.",
    ],
  };
};
