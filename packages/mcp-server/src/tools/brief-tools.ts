import {
  BriefArtifactSchema,
  BusinessDossierBaseSchema,
  BusinessDossierSchema,
  EnvironmentBriefSchema,
  MacroBriefSchema,
  PropertyBriefBaseSchema,
  PropertyBriefSchema,
  TransportBriefSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@sg-apis/shared";
import type {
  BriefArtifact,
  BriefFreshnessItem,
  BriefLimit,
  BriefProvenanceItem,
  EvidenceGap,
  ToolResult,
} from "@sg-apis/shared";
import { MasDataset } from "@sg-apis/shared";
import { getAcraEntities } from "../apis/acra/client.js";
import {
  getBcaLicensedBuilders,
  getBcaRegisteredContractors,
} from "../apis/bca/client.js";
import { getCeaSalespersons } from "../apis/cea/client.js";
import { getHdbResalePrices } from "../apis/hdb/client.js";
import {
  getBusArrivals,
  getTrafficIncidents,
  getTrainAlerts,
} from "../apis/lta/client.js";
import {
  getAirQuality,
  getForecast2Hr,
  getRainfall,
} from "../apis/nea/client.js";
import { geocode } from "../apis/onemap/client.js";
import { searchDatasets as searchSingStatDatasets } from "../apis/singstat/client.js";
import { getPropertyTransactions } from "../apis/ura/client.js";
import { fetchNormalizedMasRecords } from "./mas-tools.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import { lookupPlanningArea } from "./ura-tools.js";
import { z } from "zod";

const TransportBriefInputSchema = {
  busStopCode: z.string().min(5).optional(),
  serviceNo: z.string().min(1).optional(),
  format: z.enum(["json", "markdown"]).optional(),
};

const EnvironmentBriefInputSchema = {
  area: z.string().min(1).optional(),
  region: z.string().min(1).optional(),
  stationId: z.string().min(1).optional(),
  date: z.string().min(1).optional(),
  format: z.enum(["json", "markdown"]).optional(),
};

const renderSectionRows = (rows: readonly Record<string, unknown>[]): string => {
  return rows.length === 0 ? "_No data_" : formatResponse(rows as Record<string, unknown>[], "markdown");
};

const renderRecordSection = (label: string, value: unknown): string => {
  const heading = `### ${label}`;
  if (Array.isArray(value)) {
    return `${heading}\n${renderSectionRows(value as readonly Record<string, unknown>[])}`;
  }
  if (value !== null && typeof value === "object") {
    return `${heading}\n${formatResponse([value as Record<string, unknown>], "markdown")}`;
  }
  return `${heading}\n_No data_`;
};

const renderBriefMarkdown = (payload: BriefArtifact): string => {
  const sections = [
    `## ${payload.title}`,
    "",
    "### Summary",
    renderSectionRows(payload.summary.map((item) => ({
      label: item.label,
      value: item.value,
      source: item.source,
    }))),
    "",
    "### Evidence",
    renderSectionRows(payload.evidence.map((item) => ({
      label: item.label,
      value: item.value,
      source: item.source,
    }))),
    "",
    "### Gaps",
    renderSectionRows(payload.gaps.map((gap) => ({
      code: gap.code,
      message: gap.message,
    }))),
    "",
    "### Sources",
    renderSectionRows(payload.provenance.map((item) => ({
      source: item.source,
      tool: item.tool,
      coverage: item.coverage,
      authRequired: item.authRequired,
      recordCount: item.recordCount,
    }))),
    "",
    "### Freshness",
    renderSectionRows(payload.freshness.map((item) => ({
      source: item.source,
      observedAt: item.observedAt,
      upstreamTimestamp: item.upstreamTimestamp,
    }))),
    "",
    "### What This Does Not Do",
    renderSectionRows(payload.limits.map((item) => ({
      code: item.code,
      message: item.message,
    }))),
  ];

  for (const [label, value] of Object.entries(payload.records)) {
    sections.push("");
    sections.push(renderRecordSection(label, value));
  }

  return sections.join("\n");
};

const toToolResult = (
  payload: BriefArtifact,
  format: "json" | "markdown",
): ToolResult => {
  const validated = BriefArtifactSchema.parse(payload) as BriefArtifact;
  return {
    content: [{
      type: "text",
      text: format === "json"
        ? formatResponse(validated as unknown as Record<string, unknown>, "json")
        : renderBriefMarkdown(validated),
    }],
    structuredContent: {
      record: validated,
    },
  };
};

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

const averageNullableNumbers = (values: readonly (number | null | undefined)[]): number | null => {
  const numeric = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (numeric.length === 0) {
    return null;
  }
  return Math.round((numeric.reduce((sum, value) => sum + value, 0) / numeric.length) * 100) / 100;
};

const toShortRegion = (region: string | undefined): string | null => {
  if (region === undefined) {
    return null;
  }
  const normalized = region.replace(/\s+region$/i, "").trim();
  return normalized === "" ? null : normalized;
};

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> => {
  return typeof value === "object" && value !== null && !Array.isArray(value);
};

const findFirstNumericField = (
  record: Readonly<Record<string, unknown>> | undefined,
): { key: string; value: number } | null => {
  if (record === undefined) {
    return null;
  }

  for (const [key, value] of Object.entries(record)) {
    if (key === "date") {
      continue;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return { key, value };
    }
  }
  return null;
};

const getFirstTimestamp = (
  value: unknown,
  fields: readonly string[],
): string | null => {
  const rows = Array.isArray(value) ? value : [value];
  for (const row of rows) {
    if (!isRecord(row)) {
      continue;
    }
    for (const field of fields) {
      const candidate = row[field];
      if (typeof candidate === "string" && candidate.trim() !== "") {
        return candidate;
      }
    }
  }
  return null;
};

const getFirstBusArrivalTimestamp = (value: unknown): string | null => {
  if (!Array.isArray(value)) {
    return null;
  }
  for (const row of value) {
    if (!isRecord(row)) {
      continue;
    }
    const arrivals = row["arrivals"];
    if (!Array.isArray(arrivals)) {
      continue;
    }
    for (const arrival of arrivals) {
      if (!isRecord(arrival)) {
        continue;
      }
      const estimatedArrival = arrival["estimatedArrival"];
      if (typeof estimatedArrival === "string" && estimatedArrival.trim() !== "") {
        return estimatedArrival;
      }
    }
  }
  return null;
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

const buildBusinessLimits = (): readonly BriefLimit[] => [
  toLimit("EXACT_MATCH_ONLY", "Registry checks are exact-match oriented for company, UEN, salesperson, and estate-agent identifiers."),
  toLimit("NO_CORPORATE_GRAPH", "This dossier does not infer subsidiaries, shareholders, officers, or beneficial ownership relationships."),
  toLimit("PUBLIC_REGISTRY_SCOPE", "The brief only covers ACRA, BCA, and CEA public registry evidence exposed through the current direct tools."),
];

const buildPropertyLimits = (includeTransport: boolean, includeEnvironment: boolean): readonly BriefLimit[] => {
  const limits: BriefLimit[] = [
    toLimit("NOT_A_RECOMMENDATION", "This brief is bounded diligence context, not a valuation, investment score, or purchase recommendation."),
    toLimit("AREA_LEVEL_CONTEXT", "Property context is planning-area oriented and does not replace parcel-level legal or title checks."),
  ];
  if (!includeTransport) {
    limits.push(toLimit("TRANSPORT_NOT_INCLUDED", "Live transport context was not requested for this property brief."));
  }
  if (!includeEnvironment) {
    limits.push(toLimit("ENVIRONMENT_NOT_INCLUDED", "Live weather and air-quality context was not requested for this property brief."));
  }
  return limits;
};

const buildMacroLimits = (): readonly BriefLimit[] => [
  toLimit("STARTER_SNAPSHOT", "This brief is a compact macro starter, not a full economic research note or narrative analysis."),
  toLimit("DATASET_ENTRYPOINTS_ONLY", "SingStat coverage is limited to bounded dataset discovery in this brief rather than full table extraction."),
  toLimit("NO_FORWARD_VIEW", "The brief reports current or requested historical values and does not forecast or interpret future macro conditions."),
];

const buildTransportLimits = (hasBusStopCode: boolean): readonly BriefLimit[] => {
  const limits: BriefLimit[] = [
    toLimit("SNAPSHOT_ONLY", "This brief summarizes current LTA operational conditions and does not predict delays or incident resolution time."),
    toLimit("NO_ROUTE_PLANNING", "Use sg_onemap_route for route planning; this brief only summarizes transport operations status."),
  ];
  if (!hasBusStopCode) {
    limits.push(toLimit("NO_STOP_LEVEL_ARRIVALS", "No specific bus stop was supplied, so stop-level arrival timings are not included."));
  }
  return limits;
};

const buildEnvironmentLimits = (hasArea: boolean, hasRegion: boolean, hasStation: boolean): readonly BriefLimit[] => {
  const limits: BriefLimit[] = [
    toLimit("LIVE_SNAPSHOT_ONLY", "This brief summarizes current NEA conditions and does not replace severe-weather alerts or long-range forecasting."),
  ];
  if (!hasArea) {
    limits.push(toLimit("NO_AREA_FILTER", "No specific forecast area was supplied, so the brief reports the first available forecast area summary."));
  }
  if (!hasRegion) {
    limits.push(toLimit("NO_REGION_FILTER", "No specific air-quality region was supplied, so the brief reports the first available regional reading."));
  }
  if (!hasStation) {
    limits.push(toLimit("NO_STATION_FILTER", "No rainfall station ID was supplied, so the brief reports the first available station reading."));
  }
  return limits;
};

export const handleBusinessDossier = async (
  params: Readonly<{
    entityName?: string | undefined;
    uen?: string | undefined;
    salespersonName?: string | undefined;
    registrationNo?: string | undefined;
    estateAgentName?: string | undefined;
    estateAgentLicenseNo?: string | undefined;
    classCode?: string | undefined;
    workhead?: string | undefined;
    grade?: string | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  const companyName = params.entityName;

  const [acraRecords, bcaLicensedBuilders, bcaRegisteredContractors, ceaSalespersons] = await Promise.all([
    params.entityName !== undefined || params.uen !== undefined
      ? safeRead(
          "ACRA_UNAVAILABLE",
          "ACRA lookup failed",
          () => getAcraEntities({ entityName: params.entityName, uen: params.uen, limit: 5 }),
          gaps,
        )
      : Promise.resolve(null),
    params.entityName !== undefined || params.uen !== undefined || params.classCode !== undefined
      ? safeRead(
          "BCA_BUILDERS_UNAVAILABLE",
          "BCA licensed-builder lookup failed",
          () => getBcaLicensedBuilders({
            companyName,
            uenNo: params.uen,
            classCode: params.classCode,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    params.entityName !== undefined || params.uen !== undefined || params.workhead !== undefined || params.grade !== undefined
      ? safeRead(
          "BCA_CONTRACTORS_UNAVAILABLE",
          "BCA registered-contractor lookup failed",
          () => getBcaRegisteredContractors({
            companyName,
            uenNo: params.uen,
            workhead: params.workhead,
            grade: params.grade,
            limit: 5,
          }),
          gaps,
        )
      : Promise.resolve(null),
    params.salespersonName !== undefined
      || params.registrationNo !== undefined
      || params.estateAgentName !== undefined
      || params.estateAgentLicenseNo !== undefined
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
  ]);

  const acra = acraRecords ?? [];
  const builders = bcaLicensedBuilders ?? [];
  const contractors = bcaRegisteredContractors ?? [];
  const salespersons = ceaSalespersons ?? [];

  if ((params.entityName !== undefined || params.uen !== undefined) && acra.length === 0) {
    gaps.push(toGap("ACRA_NO_MATCH", "No exact ACRA entity matched the provided company name or UEN."));
  }
  if ((params.entityName !== undefined || params.uen !== undefined || params.classCode !== undefined) && builders.length === 0) {
    gaps.push(toGap("BCA_BUILDERS_NO_MATCH", "No licensed-builder record matched the provided company, UEN, or class code."));
  }
  if ((params.entityName !== undefined || params.uen !== undefined || params.workhead !== undefined || params.grade !== undefined) && contractors.length === 0) {
    gaps.push(toGap("BCA_CONTRACTORS_NO_MATCH", "No registered-contractor record matched the provided company, UEN, workhead, or grade."));
  }
  if ((params.salespersonName !== undefined || params.registrationNo !== undefined || params.estateAgentName !== undefined || params.estateAgentLicenseNo !== undefined) && salespersons.length === 0) {
    gaps.push(toGap("CEA_NO_MATCH", "No CEA salesperson or estate-agent record matched the provided identifier."));
  }

  const primaryAcra = acra[0];
  const primaryBuilder = builders[0];
  const primaryContractor = contractors[0];
  const primarySalesperson = salespersons[0];

  const payload: BriefArtifact = {
    title: "Business Dossier",
    summary: [
      { label: "Entity", value: primaryAcra?.entityName ?? params.entityName ?? null, source: "ACRA" },
      { label: "UEN", value: primaryAcra?.uen ?? params.uen ?? null, source: "ACRA" },
      { label: "Entity status", value: primaryAcra?.entityStatusDescription ?? null, source: "ACRA" },
      { label: "Licensed builder", value: primaryBuilder?.classCode ?? null, source: "BCA" },
      { label: "Registered contractor", value: primaryContractor?.workhead ?? null, source: "BCA" },
      { label: "Estate agent", value: primarySalesperson?.estateAgentName ?? params.estateAgentName ?? null, source: "CEA" },
    ],
    evidence: [
      { label: "ACRA matches", value: acra.length, source: "ACRA" },
      { label: "BCA licensed-builder matches", value: builders.length, source: "BCA" },
      { label: "BCA contractor matches", value: contractors.length, source: "BCA" },
      { label: "CEA matches", value: salespersons.length, source: "CEA" },
      { label: "Officer count", value: primaryAcra?.noOfOfficers ?? null, source: "ACRA" },
      { label: "Builder expiry", value: primaryBuilder?.expiryDate ?? null, source: "BCA" },
    ],
    records: {
      acra,
      bcaLicensedBuilders: builders,
      bcaRegisteredContractors: contractors,
      ceaSalespersons: salespersons,
    },
    gaps,
    provenance: [
      toProvenance("ACRA", "sg_acra_entities", "Exact-match company and UEN registry evidence.", false, acra.length),
      toProvenance("BCA", "sg_bca_licensed_builders", "Licensed-builder registry evidence for the named entity or class code.", false, builders.length),
      toProvenance("BCA", "sg_bca_registered_contractors", "Registered-contractor registry evidence for the named entity, workhead, or grade.", false, contractors.length),
      toProvenance("CEA", "sg_cea_salespersons", "Salesperson and estate-agent registry evidence for the supplied identifiers.", false, salespersons.length),
    ],
    freshness: [
      toFreshness("ACRA", observedAt, getFirstTimestamp(acra, ["annualReturnDate", "accountDueDate", "registrationIncorporationDate"])),
      toFreshness("BCA licensed builders", observedAt, getFirstTimestamp(builders, ["expiryDate"])),
      toFreshness("BCA registered contractors", observedAt, getFirstTimestamp(contractors, ["expiryDate"])),
      toFreshness("CEA", observedAt, getFirstTimestamp(salespersons, ["registrationEndDate", "registrationStartDate"])),
    ],
    limits: buildBusinessLimits(),
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

export const handlePropertyBrief = async (
  params: Readonly<{
    planningArea?: string | undefined;
    postalCode?: string | undefined;
    address?: string | undefined;
    flatType?: string | undefined;
    propertyType?: "residential" | "commercial" | "industrial" | undefined;
    includeTransport?: boolean | undefined;
    includeEnvironment?: boolean | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  const includeEnvironment = params.includeEnvironment ?? true;
  const includeTransport = params.includeTransport ?? false;

  const geocodeResults =
    params.planningArea !== undefined
      ? null
      : await safeRead(
          "ONEMAP_GEOCODE_FAILED",
          "OneMap geocode failed",
          () => geocode(params.postalCode ?? params.address ?? "", 1),
          gaps,
        );

  const firstGeocode = geocodeResults?.[0] ?? null;
  if (params.planningArea === undefined && firstGeocode === null) {
    gaps.push(toGap("LOCATION_UNRESOLVED", "The supplied postal code or address did not resolve to a Singapore location."));
  }

  const planningRecords = await safeRead(
    "URA_PLANNING_FAILED",
    "URA planning-area lookup failed",
    () => lookupPlanningArea(
      params.planningArea !== undefined
        ? { planningArea: params.planningArea }
        : { lat: firstGeocode?.lat, lng: firstGeocode?.lng },
    ),
    gaps,
  );

  const planning = planningRecords?.[0];
  const planningArea = planning?.planningArea ?? params.planningArea ?? null;
  const region = toShortRegion(planning?.region);

  const uraTransactions = planningArea === null
    ? null
    : await safeRead(
        "URA_TRANSACTIONS_FAILED",
        "URA transaction lookup failed",
        () => getPropertyTransactions(params.propertyType ?? "residential", planningArea, undefined),
        gaps,
      );

  const hdbResale = planningArea === null || (params.propertyType !== undefined && params.propertyType !== "residential")
    ? null
    : await safeRead(
        "HDB_RESALE_FAILED",
        "HDB resale lookup failed",
        () => getHdbResalePrices({ town: planningArea, flatType: params.flatType, limit: 25 }),
        gaps,
      );

  const forecast = includeEnvironment && planningArea !== null
    ? await safeRead(
        "NEA_FORECAST_FAILED",
        "NEA forecast lookup failed",
        () => getForecast2Hr(planningArea),
        gaps,
      )
    : null;

  const airQuality = includeEnvironment && region !== null
    ? await safeRead(
        "NEA_AIR_QUALITY_FAILED",
        "NEA air-quality lookup failed",
        () => getAirQuality(region),
        gaps,
      )
    : null;

  const trainAlerts = includeTransport
    ? await safeRead(
        "LTA_TRAIN_ALERTS_FAILED",
        "LTA train-alert lookup failed",
        () => getTrainAlerts(),
        gaps,
      )
    : null;

  const trafficIncidents = includeTransport
    ? await safeRead(
        "LTA_TRAFFIC_FAILED",
        "LTA traffic-incident lookup failed",
        () => getTrafficIncidents(),
        gaps,
      )
    : null;

  const resaleAverage = averageNullableNumbers((hdbResale ?? []).map((row) => row.resalePrice));
  const privateAverage = averageNullableNumbers(
    (uraTransactions ?? []).map((row) => {
      const parsed = Number(row.price);
      return Number.isFinite(parsed) ? parsed : null;
    }),
  );
  const primaryForecast = forecast?.[0];
  const primaryAirQuality = airQuality?.[0];

  const payload: BriefArtifact = {
    title: "Property Brief",
    summary: [
      { label: "Resolved planning area", value: planningArea, source: "URA" },
      { label: "Region", value: region, source: "URA" },
      { label: "Resolved postal code", value: firstGeocode?.postal ?? params.postalCode ?? null, source: "OneMap" },
      { label: "Private transaction average", value: privateAverage, source: "URA" },
      { label: "HDB resale average", value: resaleAverage, source: "HDB" },
      { label: "Forecast", value: primaryForecast?.forecast ?? null, source: "NEA" },
      { label: "PSI 24h", value: primaryAirQuality?.psi24h ?? null, source: "NEA" },
    ],
    evidence: [
      { label: "URA transactions", value: uraTransactions?.length ?? 0, source: "URA" },
      { label: "HDB resale records", value: hdbResale?.length ?? 0, source: "HDB" },
      { label: "2-hour forecast rows", value: forecast?.length ?? 0, source: "NEA" },
      { label: "Air-quality rows", value: airQuality?.length ?? 0, source: "NEA" },
      { label: "Train alerts", value: trainAlerts?.alerts.length ?? 0, source: "LTA" },
      { label: "Traffic incidents", value: trafficIncidents?.length ?? 0, source: "LTA" },
    ],
    records: {
      geocode: firstGeocode === null ? [] : [firstGeocode],
      planningArea: planningRecords ?? [],
      uraTransactions: uraTransactions ?? [],
      hdbResale: hdbResale ?? [],
      forecast: forecast ?? [],
      airQuality: airQuality ?? [],
      trainAlerts: trainAlerts?.alerts ?? [],
      trainAlertMessages: trainAlerts?.messages ?? [],
      trafficIncidents: trafficIncidents ?? [],
    },
    gaps,
    provenance: [
      toProvenance("OneMap", "sg_onemap_geocode", "Postal-code or address resolution into a Singapore geocode candidate.", true, firstGeocode === null ? 0 : 1),
      toProvenance("URA", "sg_ura_planning_area", "Planning-area resolution for the requested location.", true, planningRecords?.length ?? 0),
      toProvenance("URA", "sg_ura_property_transactions", "Private market transaction context for the resolved planning area.", true, uraTransactions?.length ?? 0),
      toProvenance("HDB", "sg_hdb_resale_prices", "Curated HDB resale market context for the resolved planning area.", false, hdbResale?.length ?? 0),
      ...(includeEnvironment
        ? [
            toProvenance("NEA", "sg_nea_forecast_2hr", "2-hour forecast coverage for the resolved planning area.", false, forecast?.length ?? 0),
            toProvenance("NEA", "sg_nea_air_quality", "Regional air-quality coverage for the resolved region.", false, airQuality?.length ?? 0),
          ]
        : []),
      ...(includeTransport
        ? [
            toProvenance("LTA", "sg_lta_train_alerts", "Network-wide train service alert coverage.", true, (trainAlerts?.alerts.length ?? 0) + (trainAlerts?.messages.length ?? 0)),
            toProvenance("LTA", "sg_lta_traffic_incidents", "Live traffic incident coverage across Singapore.", true, trafficIncidents?.length ?? 0),
          ]
        : []),
    ],
    freshness: [
      toFreshness("OneMap geocode", observedAt, null),
      toFreshness("URA planning area", observedAt, null),
      toFreshness("URA transactions", observedAt, getFirstTimestamp(uraTransactions, ["contractDate", "date"])),
      toFreshness("HDB resale", observedAt, getFirstTimestamp(hdbResale, ["month"])),
      ...(includeEnvironment
        ? [
            toFreshness("NEA forecast", observedAt, getFirstTimestamp(forecast, ["updatedAt", "validFrom"])),
            toFreshness("NEA air quality", observedAt, getFirstTimestamp(airQuality, ["updatedAt"])),
          ]
        : []),
      ...(includeTransport
        ? [
            toFreshness("LTA train alerts", observedAt, getFirstTimestamp(trainAlerts?.messages, ["createdDate"])),
            toFreshness("LTA traffic incidents", observedAt, null),
          ]
        : []),
    ],
    limits: buildPropertyLimits(includeTransport, includeEnvironment),
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

export const handleMacroBrief = async (
  params: Readonly<{
    currency?: string | undefined;
    date?: string | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];
  const currency = (params.currency ?? "USD").toUpperCase();

  const [exchangeRates, interestRates, financialStats, gdpDatasets, cpiDatasets] = await Promise.all([
    safeRead(
      "MAS_EXCHANGE_FAILED",
      "MAS exchange-rate lookup failed",
      () => fetchNormalizedMasRecords(MasDataset.EXCHANGE_RATES, {
        ...(params.date === undefined ? {} : { date: params.date }),
        ...(params.startDate === undefined ? {} : { startDate: params.startDate }),
        ...(params.endDate === undefined ? {} : { endDate: params.endDate }),
      }),
      gaps,
    ),
    safeRead(
      "MAS_SORA_FAILED",
      "MAS SORA lookup failed",
      () => fetchNormalizedMasRecords(MasDataset.INTEREST_RATES_SORA, {
        ...(params.date === undefined ? {} : { date: params.date }),
        ...(params.startDate === undefined ? {} : { startDate: params.startDate }),
        ...(params.endDate === undefined ? {} : { endDate: params.endDate }),
      }),
      gaps,
    ),
    safeRead(
      "MAS_BANKING_FAILED",
      "MAS banking-stat lookup failed",
      () => fetchNormalizedMasRecords(MasDataset.BANKING_STATS, {
        ...(params.date === undefined ? {} : { date: params.date }),
        ...(params.startDate === undefined ? {} : { startDate: params.startDate }),
        ...(params.endDate === undefined ? {} : { endDate: params.endDate }),
      }),
      gaps,
    ),
    safeRead(
      "SINGSTAT_GDP_FAILED",
      "SingStat GDP dataset discovery failed",
      () => searchSingStatDatasets("Singapore GDP", 3),
      gaps,
    ),
    safeRead(
      "SINGSTAT_CPI_FAILED",
      "SingStat CPI dataset discovery failed",
      () => searchSingStatDatasets("Singapore CPI inflation", 3),
      gaps,
    ),
  ]);

  const latestExchange = exchangeRates?.[0];
  const latestInterest = interestRates?.[0];
  const latestBanking = financialStats?.[0];
  const exchangeKey = `${currency.toLowerCase()}_sgd`;
  const exchangeValue = latestExchange?.[exchangeKey]
    ?? latestExchange?.[`${currency.toLowerCase()}_sgd_100`]
    ?? null;
  const soraMetric = findFirstNumericField(latestInterest);
  const bankingMetric = findFirstNumericField(latestBanking);

  const payload: BriefArtifact = {
    title: "Macro Brief",
    summary: [
      { label: `${currency}/SGD`, value: typeof exchangeValue === "number" ? exchangeValue : exchangeValue as string | null, source: "MAS" },
      { label: "FX date", value: typeof latestExchange?.["date"] === "string" ? latestExchange["date"] : null, source: "MAS" },
      { label: "SORA metric", value: soraMetric?.value ?? null, source: "MAS" },
      { label: "Banking metric", value: bankingMetric?.value ?? null, source: "MAS" },
      { label: "GDP dataset", value: gdpDatasets?.[0]?.title ?? null, source: "SingStat" },
      { label: "GDP table ID", value: gdpDatasets?.[0]?.id ?? null, source: "SingStat" },
      { label: "CPI dataset", value: cpiDatasets?.[0]?.title ?? null, source: "SingStat" },
      { label: "CPI table ID", value: cpiDatasets?.[0]?.id ?? null, source: "SingStat" },
    ],
    evidence: [
      { label: "FX rows", value: exchangeRates?.length ?? 0, source: "MAS" },
      { label: "SORA rows", value: interestRates?.length ?? 0, source: "MAS" },
      { label: "Banking rows", value: financialStats?.length ?? 0, source: "MAS" },
      { label: "GDP candidates", value: gdpDatasets?.length ?? 0, source: "SingStat" },
      { label: "CPI candidates", value: cpiDatasets?.length ?? 0, source: "SingStat" },
      { label: "Primary banking metric", value: bankingMetric?.key ?? null, source: "MAS" },
    ],
    records: {
      exchangeRates: exchangeRates ?? [],
      interestRates: interestRates ?? [],
      financialStats: financialStats ?? [],
      gdpDatasets: gdpDatasets ?? [],
      cpiDatasets: cpiDatasets ?? [],
    },
    gaps,
    provenance: [
      toProvenance("MAS", "sg_mas_exchange_rates", "Exchange-rate coverage for the requested currency and date range.", false, exchangeRates?.length ?? 0),
      toProvenance("MAS", "sg_mas_interest_rates", "SORA interest-rate coverage for the requested date range.", false, interestRates?.length ?? 0),
      toProvenance("MAS", "sg_mas_financial_stats", "Banking-statistics coverage for the requested date range.", false, financialStats?.length ?? 0),
      toProvenance("SingStat", "sg_singstat_search", "Bounded dataset discovery for GDP and CPI entrypoints.", false, (gdpDatasets?.length ?? 0) + (cpiDatasets?.length ?? 0)),
    ],
    freshness: [
      toFreshness("MAS exchange rates", observedAt, getFirstTimestamp(exchangeRates, ["date"])),
      toFreshness("MAS interest rates", observedAt, getFirstTimestamp(interestRates, ["date"])),
      toFreshness("MAS banking stats", observedAt, getFirstTimestamp(financialStats, ["date"])),
      toFreshness("SingStat GDP search", observedAt, null),
      toFreshness("SingStat CPI search", observedAt, null),
    ],
    limits: buildMacroLimits(),
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

export const handleTransportBrief = async (
  params: Readonly<{
    busStopCode?: string | undefined;
    serviceNo?: string | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];

  const [busArrivals, trainAlerts, trafficIncidents] = await Promise.all([
    params.busStopCode === undefined
      ? Promise.resolve(null)
      : safeRead(
          "LTA_BUS_ARRIVALS_FAILED",
          "LTA bus-arrival lookup failed",
          () => getBusArrivals(params.busStopCode!, params.serviceNo),
          gaps,
        ),
    safeRead(
      "LTA_TRAIN_ALERTS_FAILED",
      "LTA train-alert lookup failed",
      () => getTrainAlerts(),
      gaps,
    ),
    safeRead(
      "LTA_TRAFFIC_FAILED",
      "LTA traffic-incident lookup failed",
      () => getTrafficIncidents(),
      gaps,
    ),
  ]);

  const nextArrival = getFirstBusArrivalTimestamp(busArrivals);
  const primaryTrainLine = trainAlerts?.alerts[0]?.line ?? null;
  const primaryIncidentType = trafficIncidents?.[0]?.type ?? null;

  const payload: BriefArtifact = {
    title: "Transport Brief",
    summary: [
      { label: "Bus stop", value: params.busStopCode ?? null, source: "LTA" },
      { label: "Service number", value: params.serviceNo ?? null, source: "LTA" },
      { label: "Next bus ETA", value: nextArrival, source: "LTA" },
      { label: "Primary train line", value: primaryTrainLine, source: "LTA" },
      { label: "Primary incident type", value: primaryIncidentType, source: "LTA" },
    ],
    evidence: [
      { label: "Bus services", value: busArrivals?.length ?? 0, source: "LTA" },
      { label: "Train alerts", value: trainAlerts?.alerts.length ?? 0, source: "LTA" },
      { label: "Train messages", value: trainAlerts?.messages.length ?? 0, source: "LTA" },
      { label: "Traffic incidents", value: trafficIncidents?.length ?? 0, source: "LTA" },
    ],
    records: {
      busArrivals: busArrivals ?? [],
      trainAlerts: trainAlerts?.alerts ?? [],
      trainAlertMessages: trainAlerts?.messages ?? [],
      trafficIncidents: trafficIncidents ?? [],
    },
    gaps,
    provenance: [
      toProvenance("LTA", "sg_lta_bus_arrivals", "Optional stop-level bus arrival timings for the supplied stop code and service.", true, busArrivals?.length ?? 0),
      toProvenance("LTA", "sg_lta_train_alerts", "Network-wide train service alert coverage and operator messages.", true, (trainAlerts?.alerts.length ?? 0) + (trainAlerts?.messages.length ?? 0)),
      toProvenance("LTA", "sg_lta_traffic_incidents", "Live road traffic incident coverage across Singapore.", true, trafficIncidents?.length ?? 0),
    ],
    freshness: [
      toFreshness("LTA bus arrivals", observedAt, nextArrival),
      toFreshness("LTA train alerts", observedAt, getFirstTimestamp(trainAlerts?.messages, ["createdDate"])),
      toFreshness("LTA traffic incidents", observedAt, null),
    ],
    limits: buildTransportLimits(params.busStopCode !== undefined),
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

export const handleEnvironmentBrief = async (
  params: Readonly<{
    area?: string | undefined;
    region?: string | undefined;
    stationId?: string | undefined;
    date?: string | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const observedAt = new Date().toISOString();
  const gaps: EvidenceGap[] = [];

  const [forecast, airQuality, rainfall] = await Promise.all([
    safeRead(
      "NEA_FORECAST_FAILED",
      "NEA forecast lookup failed",
      () => getForecast2Hr(params.area, params.date),
      gaps,
    ),
    safeRead(
      "NEA_AIR_QUALITY_FAILED",
      "NEA air-quality lookup failed",
      () => getAirQuality(params.region, params.date),
      gaps,
    ),
    safeRead(
      "NEA_RAINFALL_FAILED",
      "NEA rainfall lookup failed",
      () => getRainfall(params.stationId, params.date),
      gaps,
    ),
  ]);

  const primaryForecast = forecast?.[0];
  const primaryAirQuality = airQuality?.[0];
  const primaryRainfall = rainfall?.[0];

  const payload: BriefArtifact = {
    title: "Environment Brief",
    summary: [
      { label: "Forecast area", value: primaryForecast?.area ?? params.area ?? null, source: "NEA" },
      { label: "Forecast", value: primaryForecast?.forecast ?? null, source: "NEA" },
      { label: "Air-quality region", value: primaryAirQuality?.region ?? params.region ?? null, source: "NEA" },
      { label: "PSI 24h", value: primaryAirQuality?.psi24h ?? null, source: "NEA" },
      { label: "Rainfall station", value: primaryRainfall?.stationName ?? params.stationId ?? null, source: "NEA" },
      { label: "Rainfall", value: primaryRainfall?.value ?? null, source: "NEA" },
    ],
    evidence: [
      { label: "Forecast rows", value: forecast?.length ?? 0, source: "NEA" },
      { label: "Air-quality rows", value: airQuality?.length ?? 0, source: "NEA" },
      { label: "Rainfall rows", value: rainfall?.length ?? 0, source: "NEA" },
      { label: "Forecast valid window", value: primaryForecast?.validText ?? null, source: "NEA" },
    ],
    records: {
      forecast: forecast ?? [],
      airQuality: airQuality ?? [],
      rainfall: rainfall ?? [],
    },
    gaps,
    provenance: [
      toProvenance("NEA", "sg_nea_forecast_2hr", "2-hour forecast coverage for the requested area or the first available forecast area.", false, forecast?.length ?? 0),
      toProvenance("NEA", "sg_nea_air_quality", "Regional air-quality coverage for the requested region or the first available regional reading.", false, airQuality?.length ?? 0),
      toProvenance("NEA", "sg_nea_rainfall", "Station rainfall coverage for the requested station or the first available station reading.", false, rainfall?.length ?? 0),
    ],
    freshness: [
      toFreshness("NEA forecast", observedAt, getFirstTimestamp(forecast, ["updatedAt", "validFrom"])),
      toFreshness("NEA air quality", observedAt, getFirstTimestamp(airQuality, ["updatedAt"])),
      toFreshness("NEA rainfall", observedAt, getFirstTimestamp(rainfall, ["timestamp"])),
    ],
    limits: buildEnvironmentLimits(params.area !== undefined, params.region !== undefined, params.stationId !== undefined),
  };

  return toToolResult(payload, resolveOutputFormat(params.format) === "json" ? "json" : "markdown");
};

export const briefToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_business_dossier",
    description: "Build a cross-registry business dossier across ACRA, BCA, and CEA using explicit company, UEN, or estate-agent identifiers.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct business-diligence tools.",
    inputSchema: BusinessDossierBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleBusinessDossier(validateInput(BusinessDossierSchema, input)),
  },
  {
    name: "sg_property_brief",
    description: "Build a location and property brief for one Singapore planning area, postal code, or address across OneMap, URA, HDB, and optional live context.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct property, map, and environment tools.",
    inputSchema: PropertyBriefBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handlePropertyBrief(validateInput(PropertyBriefSchema, input)),
  },
  {
    name: "sg_macro_brief",
    description: "Build a compact Singapore macro starter brief using MAS market data and SingStat dataset entrypoints.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct MAS and SingStat tools.",
    inputSchema: MacroBriefSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleMacroBrief(validateInput(MacroBriefSchema, input)),
  },
  {
    name: "sg_transport_brief",
    description: "Build a live transport operations brief over LTA bus arrivals, train alerts, and traffic incidents.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct LTA operational tools.",
    inputSchema: TransportBriefInputSchema,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleTransportBrief(validateInput(TransportBriefSchema, input)),
  },
  {
    name: "sg_environment_brief",
    description: "Build a live environment brief over NEA forecast, air-quality, and rainfall signals.",
    surface: "canonical",
    positioning: "High-value additive brief over the direct NEA monitoring tools.",
    inputSchema: EnvironmentBriefInputSchema,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleEnvironmentBrief(validateInput(EnvironmentBriefSchema, input)),
  },
];
