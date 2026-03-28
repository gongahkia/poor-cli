import type {
  BriefArtifact,
  BriefFreshnessItem,
  BriefLimit,
  BriefProvenanceItem,
  EvidenceGap,
  HsaNormalizedHealthProductLicenseeRecord,
  MatchConfidence,
  NextCheck,
  RiskFlag,
} from "@sg-apis/shared";
import { getAcraEntities } from "../apis/acra/client.js";
import { getBcaLicensedBuilders, getBcaRegisteredContractors } from "../apis/bca/client.js";
import { getBoaArchitects, getBoaArchitectureFirms } from "../apis/boa/client.js";
import { getCeaSalespersons } from "../apis/cea/client.js";
import { getGeBIZTenders } from "../apis/gebiz/client.js";
import { getHlbHotels } from "../apis/hlb/client.js";
import { getHsaHealthProductLicensees, getHsaLicensedPharmacies } from "../apis/hsa/client.js";
import type { BusinessDossierModule, BusinessSectorHint } from "./entity-resolution.js";
import { resolveEntityMatchConfidence, selectBusinessDossierModules } from "./entity-resolution.js";

type BusinessDossierParams = Readonly<{
  entityName?: string | undefined;
  uen?: string | undefined;
  salespersonName?: string | undefined;
  registrationNo?: string | undefined;
  estateAgentName?: string | undefined;
  estateAgentLicenseNo?: string | undefined;
  classCode?: string | undefined;
  workhead?: string | undefined;
  grade?: string | undefined;
  modules?: readonly BusinessDossierModule[] | undefined;
  sectorHints?: readonly BusinessSectorHint[] | undefined;
}>;

const toGap = (code: string, message: string): EvidenceGap => ({ code, message });
const toLimit = (code: string, message: string): BriefLimit => ({ code, message });

const safeRead = async <T>(
  code: string,
  message: string,
  read: () => Promise<T>,
  gaps: EvidenceGap[],
): Promise<T | null> => {
  try {
    return await read();
  } catch (error) {
    gaps.push(toGap(code, `${message}: ${error instanceof Error ? error.message : String(error)}`));
    return null;
  }
};

const toProvenance = (
  source: string,
  tool: string,
  coverage: string,
  authRequired: boolean,
  recordCount: number,
): BriefProvenanceItem => ({
  source,
  tool,
  coverage,
  authRequired,
  recordCount,
});

const toFreshness = (
  source: string,
  observedAt: string,
  upstreamTimestamp: string | null,
): BriefFreshnessItem => ({
  source,
  observedAt,
  upstreamTimestamp,
});

const getFirstTimestamp = (
  records: readonly Readonly<Record<string, unknown>>[] | null,
  fields: readonly string[],
): string | null => {
  if (records === null) return null;
  for (const record of records) {
    for (const field of fields) {
      const value = record[field];
      if (typeof value === "string" && value.trim() !== "") {
        return value;
      }
    }
  }
  return null;
};

const buildBusinessRiskFlags = (
  params: Pick<BusinessDossierParams, "entityName" | "uen">,
  searchedModules: ReadonlySet<BusinessDossierModule>,
  acra: readonly Readonly<Record<string, unknown>>[],
  builders: readonly Readonly<Record<string, unknown>>[],
  contractors: readonly Readonly<Record<string, unknown>>[],
  hsaLicensees: readonly HsaNormalizedHealthProductLicenseeRecord[],
): readonly RiskFlag[] => {
  const flags: RiskFlag[] = [];
  const primary = acra[0];
  if (primary !== undefined) {
    const status = String(primary["entityStatusDescription"] ?? "").toLowerCase();
    if (status !== "" && !status.includes("live") && !status.includes("registered")) {
      flags.push({
        code: "ENTITY_NOT_ACTIVE",
        severity: "high",
        message: `Entity status is "${primary["entityStatusDescription"]}", not Live or Registered.`,
        source: "ACRA",
      });
    }
  }
  if (
    searchedModules.has("acra")
    && (params.entityName !== undefined || params.uen !== undefined)
    && acra.length === 0
  ) {
    flags.push({
      code: "NO_ACRA_MATCH",
      severity: "high",
      message: "No ACRA entity matched the provided identifier.",
      source: "ACRA",
    });
  }
  for (const record of builders) {
    const expiry = record["expiryDate"];
    if (typeof expiry === "string" && expiry.trim() !== "") {
      const expiryDate = new Date(expiry);
      if (!Number.isNaN(expiryDate.getTime()) && expiryDate < new Date()) {
        flags.push({
          code: "BUILDER_LICENSE_EXPIRED",
          severity: "high",
          message: `Builder license expired on ${expiry}.`,
          source: "BCA",
        });
      }
    }
  }
  for (const record of contractors) {
    const expiry = record["expiryDate"];
    if (typeof expiry === "string" && expiry.trim() !== "") {
      const expiryDate = new Date(expiry);
      if (!Number.isNaN(expiryDate.getTime()) && expiryDate < new Date()) {
        flags.push({
          code: "CONTRACTOR_EXPIRED",
          severity: "medium",
          message: `Contractor registration expired on ${expiry}.`,
          source: "BCA",
        });
      }
    }
  }
  for (const record of hsaLicensees) {
    if (record.expiryDate === null) continue;
    const expiryDate = new Date(record.expiryDate);
    if (!Number.isNaN(expiryDate.getTime()) && expiryDate < new Date()) {
      flags.push({
        code: "HEALTH_PRODUCT_LICENCE_EXPIRED",
        severity: "medium",
        message: `${record.licenseType} expired on ${record.expiryDate}.`,
        source: "HSA",
      });
    }
  }
  return flags;
};

const buildBusinessNextChecks = (
  params: BusinessDossierParams,
  selectedModules: readonly BusinessDossierModule[],
): readonly NextCheck[] => {
  const checks: NextCheck[] = [];
  if (params.uen !== undefined) {
    checks.push({
      tool: "sg_acra_entities",
      reason: "Retrieve full ACRA entity details for deeper officer and status inspection.",
      input: { uen: params.uen },
    });
  }
  if (params.entityName !== undefined) {
    if (selectedModules.includes("bca")) {
      checks.push({
        tool: "sg_bca_licensed_builders",
        reason: "Inspect all licensed-builder records for the entity.",
        input: { companyName: params.entityName },
      });
      checks.push({
        tool: "sg_bca_registered_contractors",
        reason: "Inspect all registered-contractor records for the entity.",
        input: { companyName: params.entityName },
      });
    }
    if (selectedModules.includes("gebiz")) {
      checks.push({
        tool: "sg_gebiz_tenders",
        reason: "Inspect GeBIZ tender-award history for the named supplier.",
        input: { supplierName: params.entityName },
      });
    }
    if (selectedModules.includes("boa")) {
      checks.push({
        tool: "sg_boa_architecture_firms",
        reason: "Inspect architecture-firm records for the named entity.",
        input: { firmName: params.entityName },
      });
    }
    if (selectedModules.includes("hsa")) {
      checks.push({
        tool: "sg_hsa_health_product_licensees",
        reason: "Inspect health-product licensing rows for the named entity.",
        input: { companyName: params.entityName },
      });
      checks.push({
        tool: "sg_hsa_licensed_pharmacies",
        reason: "Check whether the named entity also appears as a licensed pharmacy.",
        input: { pharmacyName: params.entityName },
      });
    }
    if (selectedModules.includes("hlb")) {
      checks.push({
        tool: "sg_hlb_hotels",
        reason: "Inspect hotel records by keeper or hotel name for the named entity.",
        input: { keeperName: params.entityName },
      });
    }
  }
  checks.push({
    tool: "sg_datagov_search",
    reason: "Search for adjacent official public datasets related to this entity and sector.",
    input: { keyword: params.entityName ?? params.uen ?? "" },
  });
  return checks;
};

const buildBusinessLimits = (
  selectedModules: readonly BusinessDossierModule[],
): readonly BriefLimit[] => [
  toLimit("EXACT_AND_BOUNDED_MATCHING", "Registry matching prioritizes exact identifiers, then exact normalized names, then bounded fuzzy-name checks."),
  toLimit("NO_CORPORATE_GRAPH", "This dossier does not infer subsidiaries, shareholders, officers, or beneficial ownership relationships."),
  toLimit("PUBLIC_DATA_ONLY", "The dossier only uses official public registries and datasets currently exposed through this server."),
  toLimit("PUBLIC_REGISTRY_SCOPE", `This dossier is limited to the selected module set: ${selectedModules.join(", ")}.`),
];

export const buildBusinessDossierArtifact = async (
  params: BusinessDossierParams,
): Promise<BriefArtifact> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  const selectedModules = selectBusinessDossierModules(params.modules, params.sectorHints);
  const selectedModuleSet = new Set<BusinessDossierModule>(selectedModules);
  const searchedModules = new Set<BusinessDossierModule>();
  const matchedModules = new Set<BusinessDossierModule>();

  const shouldSearchAcra = selectedModuleSet.has("acra") && (params.entityName !== undefined || params.uen !== undefined);
  const shouldSearchBca = selectedModuleSet.has("bca")
    && (params.entityName !== undefined || params.uen !== undefined || params.classCode !== undefined || params.workhead !== undefined || params.grade !== undefined);
  const shouldSearchCea = selectedModuleSet.has("cea")
    && (
      params.salespersonName !== undefined
      || params.registrationNo !== undefined
      || params.estateAgentName !== undefined
      || params.estateAgentLicenseNo !== undefined
    );
  const shouldSearchGebiz = selectedModuleSet.has("gebiz") && params.entityName !== undefined;
  const shouldSearchBoa = selectedModuleSet.has("boa") && (params.entityName !== undefined || params.registrationNo !== undefined);
  const shouldSearchHsa = selectedModuleSet.has("hsa") && params.entityName !== undefined;
  const shouldSearchHlb = selectedModuleSet.has("hlb") && params.entityName !== undefined;

  if (shouldSearchAcra) searchedModules.add("acra");
  if (shouldSearchBca) searchedModules.add("bca");
  if (shouldSearchCea) searchedModules.add("cea");
  if (shouldSearchGebiz) searchedModules.add("gebiz");
  if (shouldSearchBoa) searchedModules.add("boa");
  if (shouldSearchHsa) searchedModules.add("hsa");
  if (shouldSearchHlb) searchedModules.add("hlb");

  const [
    acraRecords,
    bcaLicensedBuilders,
    bcaRegisteredContractors,
    ceaSalespersons,
    gebizTenders,
    boaArchitects,
    boaArchitectureFirms,
    hsaLicensedPharmacies,
    hsaHealthProductLicensees,
    hlbHotels,
  ] = await Promise.all([
    shouldSearchAcra
      ? safeRead(
          "ACRA_UNAVAILABLE",
          "ACRA lookup failed",
          () => getAcraEntities({ entityName: params.entityName, uen: params.uen, limit: 5 }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchBca
      ? safeRead(
          "BCA_BUILDERS_UNAVAILABLE",
          "BCA licensed-builder lookup failed",
          () => getBcaLicensedBuilders({
            companyName: params.entityName,
            uenNo: params.uen,
            classCode: params.classCode,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchBca
      ? safeRead(
          "BCA_CONTRACTORS_UNAVAILABLE",
          "BCA registered-contractor lookup failed",
          () => getBcaRegisteredContractors({
            companyName: params.entityName,
            uenNo: params.uen,
            workhead: params.workhead,
            grade: params.grade,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchCea
      ? safeRead(
          "CEA_UNAVAILABLE",
          "CEA lookup failed",
          () => getCeaSalespersons({
            salespersonName: params.salespersonName,
            registrationNo: params.registrationNo,
            estateAgentName: params.estateAgentName,
            estateAgentLicenseNo: params.estateAgentLicenseNo,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchGebiz
      ? safeRead(
          "GEBIZ_UNAVAILABLE",
          "GeBIZ lookup failed",
          () => getGeBIZTenders({ supplierName: params.entityName, limit: 10 }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchBoa
      ? safeRead(
          "BOA_ARCHITECTS_UNAVAILABLE",
          "BOA architects lookup failed",
          async () => {
            if (params.registrationNo !== undefined) {
              return getBoaArchitects({ registrationNo: params.registrationNo, limit: 5 });
            }
            const byFirm = await getBoaArchitects({ firmName: params.entityName, limit: 5 });
            return byFirm.length > 0 || params.entityName === undefined
              ? byFirm
              : getBoaArchitects({ name: params.entityName, limit: 5 });
          },
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchBoa
      ? safeRead(
          "BOA_FIRMS_UNAVAILABLE",
          "BOA architecture-firm lookup failed",
          () => getBoaArchitectureFirms({ firmName: params.entityName, limit: 5 }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchHsa
      ? safeRead(
          "HSA_PHARMACIES_UNAVAILABLE",
          "HSA pharmacy lookup failed",
          () => getHsaLicensedPharmacies({ pharmacyName: params.entityName, limit: 5 }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchHsa
      ? safeRead(
          "HSA_LICENSEES_UNAVAILABLE",
          "HSA health-product licensee lookup failed",
          () => getHsaHealthProductLicensees({ companyName: params.entityName, limit: 10 }),
          gaps,
        )
      : Promise.resolve(null),
    shouldSearchHlb
      ? safeRead(
          "HLB_UNAVAILABLE",
          "HLB hotel lookup failed",
          async () => {
            const byKeeper = await getHlbHotels({ keeperName: params.entityName, limit: 5 });
            return byKeeper.length > 0 || params.entityName === undefined
              ? byKeeper
              : getHlbHotels({ name: params.entityName, limit: 5 });
          },
          gaps,
        )
      : Promise.resolve(null),
  ]);

  const acra = acraRecords ?? [];
  const builders = bcaLicensedBuilders ?? [];
  const contractors = bcaRegisteredContractors ?? [];
  const salespersons = ceaSalespersons ?? [];
  const tenders = gebizTenders ?? [];
  const architects = boaArchitects ?? [];
  const architectureFirms = boaArchitectureFirms ?? [];
  const pharmacies = hsaLicensedPharmacies ?? [];
  const licensees = hsaHealthProductLicensees ?? [];
  const hotels = hlbHotels ?? [];

  if (acra.length > 0) matchedModules.add("acra");
  if (builders.length > 0 || contractors.length > 0) matchedModules.add("bca");
  if (salespersons.length > 0) matchedModules.add("cea");
  if (tenders.length > 0) matchedModules.add("gebiz");
  if (architects.length > 0 || architectureFirms.length > 0) matchedModules.add("boa");
  if (pharmacies.length > 0 || licensees.length > 0) matchedModules.add("hsa");
  if (hotels.length > 0) matchedModules.add("hlb");

  if (shouldSearchAcra && acra.length === 0) {
    gaps.push(toGap("ACRA_NO_MATCH", "No exact ACRA entity matched the provided company name or UEN."));
  }
  if (shouldSearchBca && builders.length === 0) {
    gaps.push(toGap("BCA_BUILDERS_NO_MATCH", "No licensed-builder record matched the provided company, UEN, or class code."));
  }
  if (shouldSearchBca && contractors.length === 0) {
    gaps.push(toGap("BCA_CONTRACTORS_NO_MATCH", "No registered-contractor record matched the provided company, UEN, workhead, or grade."));
  }
  if (shouldSearchCea && salespersons.length === 0) {
    gaps.push(toGap("CEA_NO_MATCH", "No CEA salesperson or estate-agent record matched the provided identifier."));
  }
  if (shouldSearchGebiz && tenders.length === 0) {
    gaps.push(toGap("GEBIZ_NO_MATCH", "No GeBIZ supplier award rows matched the provided entity name."));
  }
  if (shouldSearchBoa && architects.length === 0 && architectureFirms.length === 0) {
    gaps.push(toGap("BOA_NO_MATCH", "No BOA architect or architecture-firm record matched the provided identifier."));
  }
  if (shouldSearchHsa && pharmacies.length === 0 && licensees.length === 0) {
    gaps.push(toGap("HSA_NO_MATCH", "No HSA pharmacy or health-product licence row matched the provided entity name."));
  }
  if (shouldSearchHlb && hotels.length === 0) {
    gaps.push(toGap("HLB_NO_MATCH", "No HLB hotel record matched the provided hotel or keeper name."));
  }

  const unmatchedModules = selectedModules.filter((module) => searchedModules.has(module) && !matchedModules.has(module));
  const unsearchedModules = selectedModules.filter((module) => !searchedModules.has(module));

  const matchConfidence: MatchConfidence[] = [
    ...(shouldSearchAcra
      ? [resolveEntityMatchConfidence("ACRA", acra, {
          exactInputs: params.uen === undefined ? [] : [{ value: params.uen, fields: ["uen"] }],
          nameInputs: params.entityName === undefined ? [] : [{ value: params.entityName, fields: ["entityName"] }],
        })]
      : []),
    ...(shouldSearchBca
      ? [
          resolveEntityMatchConfidence("BCA licensed builders", builders, {
            exactInputs: params.uen === undefined ? [] : [{ value: params.uen, fields: ["uenNo"] }],
            nameInputs: params.entityName === undefined ? [] : [{ value: params.entityName, fields: ["companyName"] }],
          }),
          resolveEntityMatchConfidence("BCA registered contractors", contractors, {
            exactInputs: params.uen === undefined ? [] : [{ value: params.uen, fields: ["uenNo"] }],
            nameInputs: params.entityName === undefined ? [] : [{ value: params.entityName, fields: ["companyName"] }],
          }),
        ]
      : []),
    ...(shouldSearchCea
      ? [resolveEntityMatchConfidence("CEA", salespersons, {
          exactInputs: [
            ...(params.registrationNo === undefined ? [] : [{ value: params.registrationNo, fields: ["registrationNo"] }]),
            ...(params.estateAgentLicenseNo === undefined ? [] : [{ value: params.estateAgentLicenseNo, fields: ["estateAgentLicenseNo"] }]),
          ],
          nameInputs: [
            ...(params.salespersonName === undefined ? [] : [{ value: params.salespersonName, fields: ["salespersonName"] }]),
            ...(params.estateAgentName === undefined ? [] : [{ value: params.estateAgentName, fields: ["estateAgentName"] }]),
          ],
        })]
      : []),
    ...(shouldSearchGebiz
      ? [resolveEntityMatchConfidence("GeBIZ", tenders as readonly Readonly<Record<string, unknown>>[], {
          nameInputs: params.entityName === undefined ? [] : [{ value: params.entityName, fields: ["supplierName"] }],
        })]
      : []),
    ...(shouldSearchBoa
      ? [
          resolveEntityMatchConfidence("BOA architects", architects as readonly Readonly<Record<string, unknown>>[], {
            exactInputs: params.registrationNo === undefined ? [] : [{ value: params.registrationNo, fields: ["registrationNo"] }],
            nameInputs: params.entityName === undefined ? [] : [
              { value: params.entityName, fields: ["architectName"] },
              { value: params.entityName, fields: ["firmName"] },
            ],
          }),
          resolveEntityMatchConfidence("BOA architecture firms", architectureFirms as readonly Readonly<Record<string, unknown>>[], {
            nameInputs: params.entityName === undefined ? [] : [{ value: params.entityName, fields: ["firmName"] }],
          }),
        ]
      : []),
    ...(shouldSearchHsa
      ? [
          resolveEntityMatchConfidence("HSA licensed pharmacies", pharmacies as readonly Readonly<Record<string, unknown>>[], {
            nameInputs: params.entityName === undefined ? [] : [{ value: params.entityName, fields: ["pharmacyName"] }],
          }),
          resolveEntityMatchConfidence("HSA health product licensees", licensees as readonly Readonly<Record<string, unknown>>[], {
            nameInputs: params.entityName === undefined ? [] : [{ value: params.entityName, fields: ["companyName"] }],
          }),
        ]
      : []),
    ...(shouldSearchHlb
      ? [resolveEntityMatchConfidence("HLB hotels", hotels as readonly Readonly<Record<string, unknown>>[], {
          nameInputs: params.entityName === undefined ? [] : [
            { value: params.entityName, fields: ["name"] },
            { value: params.entityName, fields: ["keeperName"] },
          ],
        })]
      : []),
  ];

  const primaryAcra = acra[0];
  const primaryBuilder = builders[0];
  const primaryContractor = contractors[0];
  const primarySalesperson = salespersons[0];
  const primaryArchitect = architects[0];
  const primaryArchitectureFirm = architectureFirms[0];
  const primaryPharmacy = pharmacies[0];
  const primaryLicensee = licensees[0];
  const primaryHotel = hotels[0];
  const primaryTender = tenders[0];

  return {
    title: "Business Dossier",
    summary: [
      { label: "Entity", value: primaryAcra?.entityName ?? primaryArchitectureFirm?.firmName ?? primaryLicensee?.companyName ?? params.entityName ?? null, source: primaryAcra !== undefined ? "ACRA" : primaryArchitectureFirm !== undefined ? "BOA" : primaryLicensee !== undefined ? "HSA" : "Requested" },
      { label: "UEN", value: primaryAcra?.uen ?? params.uen ?? null, source: "ACRA" },
      { label: "Entity status", value: primaryAcra?.entityStatusDescription ?? null, source: "ACRA" },
      { label: "Licensed builder", value: primaryBuilder?.classCode ?? null, source: "BCA" },
      { label: "Registered contractor", value: primaryContractor?.workhead ?? null, source: "BCA" },
      { label: "Estate agent", value: primarySalesperson?.estateAgentName ?? params.estateAgentName ?? null, source: "CEA" },
      { label: "Architecture firm", value: primaryArchitectureFirm?.firmName ?? primaryArchitect?.firmName ?? null, source: "BOA" },
      { label: "Health-product licence", value: primaryLicensee?.licenseType ?? null, source: "HSA" },
      { label: "Licensed pharmacy", value: primaryPharmacy?.pharmacyName ?? null, source: "HSA" },
      { label: "Hotel keeper", value: primaryHotel?.keeperName ?? null, source: "HLB" },
    ],
    evidence: [
      { label: "Selected modules", value: selectedModules.length, source: "Resolver" },
      { label: "Matched modules", value: matchedModules.size, source: "Resolver" },
      { label: "ACRA matches", value: acra.length, source: "ACRA" },
      { label: "BCA licensed-builder matches", value: builders.length, source: "BCA" },
      { label: "BCA contractor matches", value: contractors.length, source: "BCA" },
      { label: "CEA matches", value: salespersons.length, source: "CEA" },
      { label: "GeBIZ award matches", value: tenders.length, source: "GeBIZ" },
      { label: "BOA architect matches", value: architects.length, source: "BOA" },
      { label: "BOA firm matches", value: architectureFirms.length, source: "BOA" },
      { label: "HSA pharmacy matches", value: pharmacies.length, source: "HSA" },
      { label: "HSA health-product matches", value: licensees.length, source: "HSA" },
      { label: "HLB hotel matches", value: hotels.length, source: "HLB" },
      { label: "Officer count", value: primaryAcra?.noOfOfficers ?? null, source: "ACRA" },
      { label: "Builder expiry", value: primaryBuilder?.expiryDate ?? null, source: "BCA" },
      { label: "Hotel rooms", value: primaryHotel?.totalRooms ?? null, source: "HLB" },
      { label: "Top GeBIZ tender", value: primaryTender?.tenderNo ?? null, source: "GeBIZ" },
    ],
    records: {
      resolution: {
        requestedEntityName: params.entityName ?? null,
        requestedUen: params.uen ?? null,
        requestedSalespersonName: params.salespersonName ?? null,
        requestedRegistrationNo: params.registrationNo ?? null,
        selectedModules,
        sectorHints: params.sectorHints ?? [],
        searchedModules: Array.from(searchedModules),
        matchedModules: Array.from(matchedModules),
        unmatchedModules,
        unsearchedModules,
      },
      acra,
      bcaLicensedBuilders: builders,
      bcaRegisteredContractors: contractors,
      ceaSalespersons: salespersons,
      gebizTenders: tenders,
      boaArchitects: architects,
      boaArchitectureFirms: architectureFirms,
      hsaLicensedPharmacies: pharmacies,
      hsaHealthProductLicensees: licensees,
      hlbHotels: hotels,
    },
    gaps,
    provenance: [
      ...(selectedModuleSet.has("acra")
        ? [toProvenance("ACRA", "sg_acra_entities", "Exact-match company and UEN registry evidence.", false, acra.length)]
        : []),
      ...(selectedModuleSet.has("bca")
        ? [
            toProvenance("BCA", "sg_bca_licensed_builders", "Licensed-builder registry evidence for the named entity or class code.", false, builders.length),
            toProvenance("BCA", "sg_bca_registered_contractors", "Registered-contractor registry evidence for the named entity, workhead, or grade.", false, contractors.length),
          ]
        : []),
      ...(selectedModuleSet.has("cea")
        ? [toProvenance("CEA", "sg_cea_salespersons", "Salesperson and estate-agent registry evidence for the supplied identifiers.", false, salespersons.length)]
        : []),
      ...(selectedModuleSet.has("gebiz")
        ? [toProvenance("GeBIZ", "sg_gebiz_tenders", "Government procurement award history for the named supplier.", false, tenders.length)]
        : []),
      ...(selectedModuleSet.has("boa")
        ? [
            toProvenance("BOA", "sg_boa_architects", "Board of Architects architect registry evidence for the supplied firm or registration identifier.", false, architects.length),
            toProvenance("BOA", "sg_boa_architecture_firms", "Board of Architects architecture-firm registry evidence for the supplied firm identifier.", false, architectureFirms.length),
          ]
        : []),
      ...(selectedModuleSet.has("hsa")
        ? [
            toProvenance("HSA", "sg_hsa_licensed_pharmacies", "Licensed pharmacy evidence for the named entity.", false, pharmacies.length),
            toProvenance("HSA", "sg_hsa_health_product_licensees", "Health-product licensing evidence for the named company.", false, licensees.length),
          ]
        : []),
      ...(selectedModuleSet.has("hlb")
        ? [toProvenance("HLB", "sg_hlb_hotels", "Hotels Licensing Board hotel and keeper evidence for the named entity.", false, hotels.length)]
        : []),
    ],
    freshness: [
      ...(selectedModuleSet.has("acra")
        ? [toFreshness("ACRA", observedAt, getFirstTimestamp(acra, ["annualReturnDate", "accountDueDate", "registrationIncorporationDate"]))]
        : []),
      ...(selectedModuleSet.has("bca")
        ? [
            toFreshness("BCA licensed builders", observedAt, getFirstTimestamp(builders, ["expiryDate"])),
            toFreshness("BCA registered contractors", observedAt, getFirstTimestamp(contractors, ["expiryDate"])),
          ]
        : []),
      ...(selectedModuleSet.has("cea")
        ? [toFreshness("CEA", observedAt, getFirstTimestamp(salespersons, ["registrationEndDate", "registrationStartDate"]))]
        : []),
      ...(selectedModuleSet.has("gebiz")
        ? [toFreshness("GeBIZ", observedAt, getFirstTimestamp(tenders as readonly Readonly<Record<string, unknown>>[], ["awardDate"]))]
        : []),
      ...(selectedModuleSet.has("boa")
        ? [
            toFreshness("BOA architects", observedAt, null),
            toFreshness("BOA architecture firms", observedAt, null),
          ]
        : []),
      ...(selectedModuleSet.has("hsa")
        ? [
            toFreshness("HSA licensed pharmacies", observedAt, null),
            toFreshness("HSA health product licensees", observedAt, getFirstTimestamp(licensees as readonly Readonly<Record<string, unknown>>[], ["expiryDate"])),
          ]
        : []),
      ...(selectedModuleSet.has("hlb")
        ? [toFreshness("HLB hotels", observedAt, getFirstTimestamp(hotels as readonly Readonly<Record<string, unknown>>[], ["lastUpdatedAt"]))]
        : []),
    ],
    limits: buildBusinessLimits(selectedModules),
    riskFlags: buildBusinessRiskFlags(params, searchedModules, acra, builders, contractors, licensees),
    matchConfidence,
    nextChecks: buildBusinessNextChecks(params, selectedModules),
  };
};
