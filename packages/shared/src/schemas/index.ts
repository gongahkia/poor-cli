import { z } from "zod";
import type { ZodSchema } from "zod";
import { ValidationError } from "../errors.js";
import { COUNTRY_PACK_SCHEMA_VERSION } from "../schema-version.js";

const OutputFormatSchema = z.enum(["json", "markdown", "csv", "geojson"]);
const IsoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const DatagovFilterValueSchema = z.union([
  z.string(),
  z.number(),
  z.boolean(),
  z.object({
    ilike: z.string().min(1),
  }).strict(),
]);
const BriefValueSchema = z.union([z.string(), z.number(), z.boolean(), z.null()]);
const BriefSummaryItemSchema = z.object({
  label: z.string().min(1),
  value: BriefValueSchema,
  source: z.string().min(1),
}).strict();
const EvidenceGapSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
}).strict();
const BriefLimitSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
}).strict();
const BriefProvenanceItemSchema = z.object({
  source: z.string().min(1),
  tool: z.string().min(1),
  coverage: z.string().min(1),
  authRequired: z.boolean(),
  recordCount: z.number().int().min(0),
  sourceUrl: z.string().url().optional(),
  evidenceType: z.enum(["official_registry", "web_discovery", "operational_metadata"]).optional(),
}).strict();
const BriefFreshnessItemSchema = z.object({
  source: z.string().min(1),
  observedAt: z.string().min(1),
  upstreamTimestamp: z.string().min(1).nullable(),
}).strict();

export const SingStatSearchSchema = z.object({
  keyword: z.string().min(1),
  limit: z.number().int().positive().optional(),
});

export const SingStatTableSchema = z.object({
  tableId: z.string().min(1),
  timeFilter: z.string().optional(),
  variables: z.array(z.string()).optional(),
  format: OutputFormatSchema.optional(),
});

export const SingStatBrowseSchema = z.object({
  category: z.string().optional(),
});

export const SingStatTimeseriesSchema = z.object({
  tableId: z.string().min(1),
  indicator: z.string().min(1),
  startYear: z.number().int(),
  endYear: z.number().int(),
  format: OutputFormatSchema.optional(),
});

export const SingStatCompareSchema = z.object({
  queries: z.array(
    z.object({
      tableId: z.string().min(1),
      indicator: z.string().min(1),
      label: z.string().min(1),
    }),
  ),
  startYear: z.number().int().optional(),
  endYear: z.number().int().optional(),
  format: OutputFormatSchema.optional(),
});

export const MasExchangeRateSchema = z.object({
  currency: z.string().length(3).optional(),
  date: IsoDateSchema.optional(),
  startDate: IsoDateSchema.optional(),
  endDate: IsoDateSchema.optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const MasInterestRateSchema = z.object({
  date: IsoDateSchema.optional(),
  startDate: IsoDateSchema.optional(),
  endDate: IsoDateSchema.optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const MasFinancialStatsSchema = z.object({
  date: IsoDateSchema.optional(),
  startDate: IsoDateSchema.optional(),
  endDate: IsoDateSchema.optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const OneMapGeocodeSchema = z.object({
  searchVal: z.string().min(1),
  limit: z.number().int().positive().optional(),
});

export const OneMapReverseGeocodeSchema = z.object({
  lat: z.number(),
  lng: z.number(),
  buffer: z.number().positive().optional(),
});

export const OneMapRouteSchema = z.object({
  startLat: z.number(),
  startLng: z.number(),
  endLat: z.number(),
  endLng: z.number(),
  routeType: z.enum(["walk", "drive", "pt", "cycle"]),
}).strict();

export const OneMapPopulationSchema = z.object({
  planningArea: z.string().min(1),
  year: z.string().optional(),
  dataType: z
    .enum([
      "getEconomicStatus",
      "getEthnicGroup",
      "getHouseholdMonthlyIncomeWork",
      "getPopulationAgeGroup",
      "getSpokenAtHome",
      "getTenantHouseholdSize",
      "getTypeOfDwellingHousehold",
    ])
    .optional(),
  format: OutputFormatSchema.optional(),
});

export const OneMapConvertCoordsSchema = z.object({
  from: z.enum(["SVY21", "WGS84"]),
  x: z.number(),
  y: z.number(),
});

export const UraPropertyTransactionsSchema = z.object({
  propertyType: z.enum(["residential", "commercial", "industrial"]).optional(),
  area: z.string().optional(),
  period: z.string().optional(),
  format: OutputFormatSchema.optional(),
});

export const UraPlanningAreaBaseSchema = z.object({
  lat: z.number().optional(),
  lng: z.number().optional(),
  planningArea: z.string().optional(),
});

export const UraPlanningAreaSchema = UraPlanningAreaBaseSchema.refine(
  ({ lat, lng, planningArea }) =>
    planningArea !== undefined || (lat !== undefined && lng !== undefined),
  {
    message: "Provide planningArea or both lat and lng",
  },
);

export const UraDevChargesSchema = z.object({
  useGroup: z.string().optional(),
  sector: z.string().optional(),
});

export const DatagovSearchSchema = z.object({
  keyword: z.string().min(1),
  limit: z.number().int().positive().optional(),
});

export const DatagovGetSchema = z.object({
  datasetId: z.string().min(1),
  format: OutputFormatSchema.optional(),
}).strict();

export const DatagovResourcesSchema = z.object({
  datasetId: z.string().min(1),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const DatagovRowsBaseSchema = z.object({
  datasetId: z.string().min(1).optional(),
  resourceId: z.string().min(1).optional(),
  filters: z.record(DatagovFilterValueSchema).optional(),
  limit: z.number().int().positive().max(200).optional(),
  offset: z.number().int().min(0).optional(),
  sort: z.string().min(1).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const DatagovRowsSchema = DatagovRowsBaseSchema.refine(
  ({ datasetId, resourceId }) => datasetId !== undefined || resourceId !== undefined,
  {
    message: "Provide datasetId or resourceId.",
  },
);

export const DatagovBrowseSchema = z.object({
  collection: z.string().optional(),
});

const CivicDirectoryBaseSchema = z.object({
  name: z.string().min(1).optional(),
  postalCode: z.string().regex(/^\d{6}$/).optional(),
  lat: z.number().min(-90).max(90).optional(),
  lng: z.number().min(-180).max(180).optional(),
  radiusKm: z.number().positive().max(20).optional(),
  limit: z.number().int().positive().max(200).optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
}).strict();

const requireLatLngPair = <TSchema extends z.ZodTypeAny>(schema: TSchema): TSchema =>
  schema.refine(
    (value) => {
      const record = value as { lat?: number; lng?: number };
      return (record.lat === undefined && record.lng === undefined)
        || (record.lat !== undefined && record.lng !== undefined);
    },
    {
      message: "Provide both lat and lng together.",
    },
  ) as unknown as TSchema;

const MonthSchema = z.string().regex(/^\d{4}-\d{2}$/);

export const LtaBusArrivalsSchema = z.object({
  busStopCode: z.string().min(5),
  serviceNo: z.string().min(1).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const LtaTrainAlertsSchema = z.object({
  format: OutputFormatSchema.optional(),
}).strict();

export const LtaTrafficIncidentsSchema = z.object({
  format: OutputFormatSchema.optional(),
}).strict();

export const LtaRoadWorksSchema = z.object({
  format: OutputFormatSchema.optional(),
}).strict();

export const LtaRoadOpeningsSchema = z.object({
  format: OutputFormatSchema.optional(),
}).strict();

export const LtaTrafficImagesSchema = z.object({
  format: OutputFormatSchema.optional(),
}).strict();

export const NeaForecast2HrSchema = z.object({
  area: z.string().min(1).optional(),
  date: z.string().min(1).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const NeaAirQualitySchema = z.object({
  region: z.string().min(1).optional(),
  date: z.string().min(1).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const NeaRainfallSchema = z.object({
  stationId: z.string().min(1).optional(),
  date: z.string().min(1).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const HdbResalePricesSchema = z.object({
  town: z.string().min(1).optional(),
  flatType: z.string().min(1).optional(),
  startMonth: MonthSchema.optional(),
  endMonth: MonthSchema.optional(),
  limit: z.number().int().positive().max(200).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const HdbRentalPricesSchema = z.object({
  town: z.string().min(1).optional(),
  flatType: z.string().min(1).optional(),
  startMonth: MonthSchema.optional(),
  endMonth: MonthSchema.optional(),
  limit: z.number().int().positive().max(200).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const CeaSalespersonsBaseSchema = z.object({
  salespersonName: z.string().min(1).optional(),
  registrationNo: z.string().min(1).optional(),
  estateAgentName: z.string().min(1).optional(),
  estateAgentLicenseNo: z.string().min(1).optional(),
  limit: z.number().int().positive().max(100).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const CeaSalespersonsSchema = CeaSalespersonsBaseSchema.refine(
  ({ salespersonName, registrationNo, estateAgentName, estateAgentLicenseNo }) =>
    salespersonName !== undefined
    || registrationNo !== undefined
    || estateAgentName !== undefined
    || estateAgentLicenseNo !== undefined,
  {
    message: "Provide at least one exact-match filter.",
  },
);

export const BcaLicensedBuildersBaseSchema = z.object({
  companyName: z.string().min(1).optional(),
  uenNo: z.string().min(1).optional(),
  className: z.string().min(1).optional(),
  classCode: z.string().min(1).optional(),
  limit: z.number().int().positive().max(100).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const BcaLicensedBuildersSchema = BcaLicensedBuildersBaseSchema.refine(
  ({ companyName, uenNo, className, classCode }) =>
    companyName !== undefined
    || uenNo !== undefined
    || className !== undefined
    || classCode !== undefined,
  {
    message: "Provide at least one exact-match filter.",
  },
);

export const BcaRegisteredContractorsBaseSchema = z.object({
  companyName: z.string().min(1).optional(),
  uenNo: z.string().min(1).optional(),
  workhead: z.string().min(1).optional(),
  grade: z.string().min(1).optional(),
  limit: z.number().int().positive().max(100).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const BcaRegisteredContractorsSchema = BcaRegisteredContractorsBaseSchema.refine(
  ({ companyName, uenNo, workhead, grade }) =>
    companyName !== undefined
    || uenNo !== undefined
    || workhead !== undefined
    || grade !== undefined,
  {
    message: "Provide at least one exact-match filter.",
  },
);

export const AcraEntitiesBaseSchema = z.object({
  entityName: z.string().min(1).optional(),
  uen: z.string().min(1).optional(),
  limit: z.number().int().positive().max(50).optional(),
  format: OutputFormatSchema.optional(),
}).strict();

export const BusinessDossierBaseSchema = z.object({
  entityName: z.string().min(1).optional(),
  uen: z.string().min(1).optional(),
  salespersonName: z.string().min(1).optional(),
  registrationNo: z.string().min(1).optional(),
  estateAgentName: z.string().min(1).optional(),
  estateAgentLicenseNo: z.string().min(1).optional(),
  classCode: z.string().min(1).optional(),
  workhead: z.string().min(1).optional(),
  grade: z.string().min(1).optional(),
  modules: z.array(z.enum(["acra", "bca", "cea", "gebiz", "boa", "hsa", "hlb"])).min(1).optional(),
  sectorHints: z.array(z.enum(["construction", "real_estate", "architecture", "healthcare", "hospitality", "procurement"])).min(1).optional(),
  includeContextIds: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const BusinessDossierSchema = BusinessDossierBaseSchema.refine(
  ({
    entityName,
    uen,
    salespersonName,
    registrationNo,
    estateAgentName,
    estateAgentLicenseNo,
    classCode,
    workhead,
    grade,
  }) =>
    entityName !== undefined
    || uen !== undefined
    || salespersonName !== undefined
    || registrationNo !== undefined
    || estateAgentName !== undefined
    || estateAgentLicenseNo !== undefined
    || classCode !== undefined
    || workhead !== undefined
    || grade !== undefined,
  {
    message: "Provide at least one business or estate-agent identifier.",
  },
);

export const PropertyBriefBaseSchema = z.object({
  planningArea: z.string().min(1).optional(),
  postalCode: z.string().regex(/^\d{6}$/).optional(),
  address: z.string().min(1).optional(),
  flatType: z.string().min(1).optional(),
  propertyType: z.enum(["residential", "commercial", "industrial"]).optional(),
  includeTransport: z.boolean().optional(),
  includeEnvironment: z.boolean().optional(),
  includeContextIds: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const PropertyBriefSchema = PropertyBriefBaseSchema.refine(
  ({ planningArea, postalCode, address }) =>
    planningArea !== undefined || postalCode !== undefined || address !== undefined,
  {
    message: "Provide planningArea, postalCode, or address.",
  },
);

export const MacroBriefSchema = z.object({
  currency: z.string().length(3).optional(),
  date: IsoDateSchema.optional(),
  startDate: IsoDateSchema.optional(),
  endDate: IsoDateSchema.optional(),
  includeContextIds: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransportBriefBaseSchema = z.object({
  busStopCode: z.string().min(5).optional(),
  serviceNo: z.string().min(1).optional(),
  includeContextIds: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransportBriefSchema = TransportBriefBaseSchema.refine(
  ({ busStopCode, serviceNo }) => serviceNo === undefined || busStopCode !== undefined,
  {
    message: "Provide busStopCode when serviceNo is supplied.",
  },
);

export const EnvironmentBriefBaseSchema = z.object({
  area: z.string().min(1).optional(),
  region: z.string().min(1).optional(),
  stationId: z.string().min(1).optional(),
  date: z.string().min(1).optional(),
  includeContextIds: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const EnvironmentBriefSchema = EnvironmentBriefBaseSchema;

export const CivicBriefBaseSchema = z.object({
  postalCode: z.string().regex(/^\d{6}$/).optional(),
  address: z.string().min(1).optional(),
  lat: z.number().min(-90).max(90).optional(),
  lng: z.number().min(-180).max(180).optional(),
  radiusKm: z.number().positive().max(20).optional(),
  modules: z.array(z.enum(["pa", "sportsg", "ecda", "msf", "hawker"])).min(1).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const CivicBriefSchema = requireLatLngPair(CivicBriefBaseSchema);

const TransitStopIdsSchema = z.array(z.string().regex(/^\d{5}$/)).max(25);
const TransitMobilityModeSchema = z.enum(["wheelchair", "reduced-walk", "elder-friendly"]);
const TransitRecommendationTypeSchema = z.enum([
  "reliability",
  "transfer-risk",
  "playbook",
  "accessibility",
]);
const TransitObjectiveSchema = z.enum([
  "minimize_delay",
  "maximize_accessibility",
  "minimize_transfer_risk",
  "balanced",
]);

export const TransitHealthSchema = z.object({
  stopIds: TransitStopIdsSchema.optional(),
  includeTrafficImages: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitHotspotsSchema = z.object({
  stopIds: TransitStopIdsSchema.optional(),
  includeTrafficImages: z.boolean().optional(),
  gridSizeDegrees: z.number().positive().max(0.05).optional(),
  impactRadiusMeters: z.number().positive().max(3000).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitOpsBriefSchema = z.object({
  stopIds: TransitStopIdsSchema.optional(),
  scopeKey: z.string().min(1).optional(),
  includeTrafficImages: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitPackSchema = z.object({
  stopIds: TransitStopIdsSchema.optional(),
  scopeKey: z.string().min(1).optional(),
  includeTrafficImages: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitReliabilitySchema = z.object({
  originStopId: z.string().regex(/^\d{5}$/),
  destinationStopId: z.string().regex(/^\d{5}$/),
  horizonMinutes: z.number().int().positive().max(240).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitTransferRiskSchema = z.object({
  fromServiceNo: z.string().min(1),
  toServiceNo: z.string().min(1),
  transferStopId: z.string().regex(/^\d{5}$/),
  expectedWalkMinutes: z.number().positive().max(60).optional(),
  minBufferMinutes: z.number().positive().max(60).optional(),
  fallbackServiceNos: z.array(z.string().min(1)).max(20).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitAccessibleRouteSchema = z.object({
  stopIds: TransitStopIdsSchema.min(2),
  originLat: z.number().min(-90).max(90),
  originLng: z.number().min(-180).max(180),
  destinationLat: z.number().min(-90).max(90),
  destinationLng: z.number().min(-180).max(180),
  mobilityMode: TransitMobilityModeSchema,
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitPlanConstraintsSchema = z.object({
  maxWalkMeters: z.number().positive().max(5000).optional(),
  minConfidence: z.number().min(0).max(1).optional(),
  avoidHighRisk: z.boolean().optional(),
  mobilityMode: TransitMobilityModeSchema.optional(),
}).strict();

export const TransitObjectivePlanSchema = z.object({
  tenantId: z.string().min(1).optional(),
  objective: TransitObjectiveSchema,
  scopeKey: z.string().min(1).optional(),
  stopIds: TransitStopIdsSchema.optional(),
  originStopId: z.string().regex(/^\d{5}$/).optional(),
  destinationStopId: z.string().regex(/^\d{5}$/).optional(),
  transferStopId: z.string().regex(/^\d{5}$/).optional(),
  fromServiceNo: z.string().min(1).optional(),
  toServiceNo: z.string().min(1).optional(),
  horizonMinutes: z.number().int().positive().max(240).optional(),
  maxActions: z.number().int().positive().max(20).optional(),
  constraints: TransitPlanConstraintsSchema.optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitCounterfactualScenarioSchema = z.object({
  id: z.string().min(1).optional(),
  label: z.string().min(1),
  requestPatch: TransitObjectivePlanSchema.partial().optional(),
  constraintsPatch: TransitPlanConstraintsSchema.optional(),
  maxActions: z.number().int().positive().max(20).optional(),
}).strict();

export const TransitCounterfactualSimulateSchema = z.object({
  tenantId: z.string().min(1).optional(),
  baseRequest: TransitObjectivePlanSchema,
  scenarios: z.array(TransitCounterfactualScenarioSchema).min(1).max(20),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitOutcomeRecordSchema = z.object({
  scopeKey: z.string().min(1).optional(),
  recommendationType: TransitRecommendationTypeSchema,
  recommendationId: z.string().min(1).optional(),
  accepted: z.boolean(),
  success: z.boolean().optional(),
  confidence: z.number().min(0).max(1).optional(),
  predictedWaitMinutes: z.number().min(0).optional(),
  actualWaitMinutes: z.number().min(0).optional(),
  predictedRisk: z.number().min(0).max(1).optional(),
  actualRisk: z.number().min(0).max(1).optional(),
  metadata: z.record(z.unknown()).optional(),
}).strict();

export const TransitModelMetricsSchema = z.object({
  scopeKey: z.string().min(1).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitPolicyAuditSchema = z.object({
  tenantId: z.string().min(1).optional(),
  scopeKey: z.string().min(1).optional(),
  source: z.enum(["plan", "counterfactual-baseline", "counterfactual-scenario", "policy-replay"]).optional(),
  limit: z.number().int().positive().max(500).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const TransitPolicyReplaySchema = z.object({
  traceId: z.string().min(1),
  constraintsPatch: TransitPlanConstraintsSchema.optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

const RiskFlagSchema = z.object({
  code: z.string().min(1),
  severity: z.enum(["high", "medium", "low"]),
  message: z.string().min(1),
  source: z.string().min(1),
}).strict();
const MatchConfidenceSchema = z.object({
  source: z.string().min(1),
  confidence: z.enum(["exact", "name-exact", "name-fuzzy", "no-match"]),
  matchedOn: z.string().nullable(),
}).strict();
export const NextCheckSchema = z.object({
  tool: z.string().min(1),
  reason: z.string().min(1),
  input: z.record(z.unknown()),
}).strict();

export const ContextIdsSchema = z.object({
  traceId: z.string().uuid(),
  requestId: z.string().uuid(),
}).strict();

export const ToolErrorPayloadSchema = z.object({
  source: z.string().min(1),
  tool: z.string().min(1),
  code: z.string().min(1),
  retryable: z.boolean(),
  severity: z.enum(["high", "medium", "low"]).optional(),
  category: z.string().min(1).optional(),
  message: z.string().min(1),
  suggestedAction: z.string().min(1).optional(),
  statusCode: z.number().int().optional(),
  details: z.unknown().optional(),
  contextIds: ContextIdsSchema.optional(),
}).strict();

export const QueryBlockerSchema = z.object({
  field: z.string().min(1),
  reason: z.string().min(1),
  directTool: z.string().min(1),
  exampleInput: z.record(z.unknown()),
  suggestedPrompt: z.string().min(1),
}).strict();

export const QueryPlannedStepSchema = z.object({
  id: z.string().min(1),
  purpose: z.string().min(1),
  tool: z.string().min(1),
  input: z.record(z.unknown()),
  dependsOn: z.array(z.string().min(1)).optional(),
}).strict();

export const QueryExecutedStepSchema = QueryPlannedStepSchema.extend({
  status: z.enum(["completed", "failed"]),
  outputText: z.string().optional(),
  structuredOutput: z.record(z.unknown()).optional(),
  error: ToolErrorPayloadSchema.optional(),
}).strict();

export const QueryResultSummarySchema = z.object({
  level: z.string().min(1),
  headline: z.string().min(1),
}).strict();

export const BriefArtifactSchema = z.object({
  title: z.string().min(1),
  summary: z.array(BriefSummaryItemSchema),
  evidence: z.array(BriefSummaryItemSchema),
  records: z.record(z.unknown()),
  gaps: z.array(EvidenceGapSchema),
  provenance: z.array(BriefProvenanceItemSchema),
  freshness: z.array(BriefFreshnessItemSchema),
  limits: z.array(BriefLimitSchema),
  riskFlags: z.array(RiskFlagSchema).optional(),
  matchConfidence: z.array(MatchConfidenceSchema).optional(),
  nextChecks: z.array(NextCheckSchema).optional(),
}).strict();

const CountryPackAuthSchema = z.object({
  required: z.boolean(),
  kind: z.enum(["none", "api_key", "oauth", "session", "partner_license"]),
  envVars: z.array(z.string().min(1)),
  notes: z.string().min(1),
}).strict();

const CountryPackLicensingSchema = z.object({
  upstreamTermsUrl: z.string().url().nullable(),
  redistribution: z.enum(["public_allowed", "attribution_required", "partner_required", "restricted", "unknown"]),
  commercialUse: z.enum(["allowed", "partner_required", "restricted", "unknown"]),
  attributionRequired: z.boolean(),
  notes: z.string().min(1),
}).strict();

const CountryPackFreshnessSchema = z.object({
  observedAt: z.string().min(1),
  upstreamTimestamp: z.string().min(1).nullable(),
  refreshCadence: z.string().min(1),
  staleAfterDays: z.number().int().positive(),
}).strict();

const CountryPackToolSchema = z.object({
  name: z.string().regex(/^[a-z]{2}_[a-z0-9_]+$/),
  family: z.string().min(1),
  purpose: z.string().min(1),
  outputContract: z.string().min(1),
  authRequired: z.boolean(),
  publicDataLimits: z.array(BriefLimitSchema).min(1),
}).strict();

export const CountryPackEnvelopeSchema = z.object({
  schemaVersion: z.literal(COUNTRY_PACK_SCHEMA_VERSION),
  packId: z.string().regex(/^[a-z]{2}$/),
  country: z.object({
    name: z.string().min(1),
    iso2: z.string().length(2),
    iso3: z.string().length(3),
  }).strict(),
  status: z.enum(["proposal", "skeleton", "public_preview", "stable", "blocked"]),
  summary: z.string().min(1),
  auth: CountryPackAuthSchema,
  licensing: CountryPackLicensingSchema,
  freshness: CountryPackFreshnessSchema,
  publicDataLimits: z.array(BriefLimitSchema).min(1),
  tools: z.array(CountryPackToolSchema),
  examples: z.array(z.object({
    title: z.string().min(1),
    input: z.record(z.unknown()),
    expectedGaps: z.array(EvidenceGapSchema),
  }).strict()),
  contributionNotes: z.array(z.string().min(1)),
}).strict();

export const AcraEntitiesSchema = AcraEntitiesBaseSchema.refine(
  ({ entityName, uen }) => entityName !== undefined || uen !== undefined,
  {
    message: "Provide an entityName or UEN.",
  },
);

export const HealthCheckSchema = z.object({}).optional();

export const KeySetSchema = z.object({
  apiName: z.string().min(1),
  key: z.string().min(1),
});

export const KeyListSchema = z.object({}).optional();

export const KeyDeleteSchema = z.object({
  apiName: z.string().min(1),
});

export const CacheStatsSchema = z.object({}).optional();

export const CacheClearSchema = z.object({
  api: z.string().optional(),
});

export const ConfigGetSchema = z.object({}).optional();

export const ConfigSetSchema = z.object({
  key: z.string().min(1),
  value: z.string().min(1),
});

export const GeBIZTendersSchema = z.object({
  agency: z.string().min(1).optional(),
  category: z.string().min(1).optional(),
  supplierName: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const BoaArchitectsBaseSchema = z.object({
  name: z.string().min(1).optional(),
  registrationNo: z.string().min(1).optional(),
  firmName: z.string().min(1).optional(),
  limit: z.number().int().positive().max(100).optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const BoaArchitectsSchema = BoaArchitectsBaseSchema.refine(
  ({ name, registrationNo, firmName }) =>
    name !== undefined || registrationNo !== undefined || firmName !== undefined,
  {
    message: "Provide at least one architect, registration, or firm identifier.",
  },
);

export const BoaArchitectureFirmsBaseSchema = z.object({
  firmName: z.string().min(1).optional(),
  email: z.string().min(1).optional(),
  phone: z.string().min(1).optional(),
  limit: z.number().int().positive().max(100).optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const BoaArchitectureFirmsSchema = BoaArchitectureFirmsBaseSchema.refine(
  ({ firmName, email, phone }) =>
    firmName !== undefined || email !== undefined || phone !== undefined,
  {
    message: "Provide at least one architecture-firm identifier.",
  },
);

export const HsaLicensedPharmaciesBaseSchema = z.object({
  pharmacyName: z.string().min(1).optional(),
  pharmacistInCharge: z.string().min(1).optional(),
  pharmacyAddress: z.string().min(1).optional(),
  postalCode: z.string().regex(/^\d{6}$/).optional(),
  limit: z.number().int().positive().max(100).optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const HsaLicensedPharmaciesSchema = HsaLicensedPharmaciesBaseSchema.refine(
  ({ pharmacyName, pharmacistInCharge, pharmacyAddress, postalCode }) =>
    pharmacyName !== undefined
    || pharmacistInCharge !== undefined
    || pharmacyAddress !== undefined
    || postalCode !== undefined,
  {
    message: "Provide at least one pharmacy identifier.",
  },
);

export const HsaHealthProductLicenseesBaseSchema = z.object({
  companyName: z.string().min(1).optional(),
  licenseType: z.string().min(1).optional(),
  activityType: z.string().min(1).optional(),
  dosageForm: z.string().min(1).optional(),
  limit: z.number().int().positive().max(100).optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const HsaHealthProductLicenseesSchema = HsaHealthProductLicenseesBaseSchema.refine(
  ({ companyName, licenseType, activityType, dosageForm }) =>
    companyName !== undefined
    || licenseType !== undefined
    || activityType !== undefined
    || dosageForm !== undefined,
  {
    message: "Provide at least one health-product licensee identifier.",
  },
);

export const HlbHotelsInputSchema = CivicDirectoryBaseSchema.extend({
  keeperName: z.string().min(1).optional(),
});

export const HlbHotelsSchema = requireLatLngPair(HlbHotelsInputSchema);

export const PaCommunityOutletsInputSchema = CivicDirectoryBaseSchema.extend({
  type: z.enum(["community_club", "passion_wave"]).optional(),
});

export const PaCommunityOutletsSchema = requireLatLngPair(PaCommunityOutletsInputSchema);

export const PaResidentNetworkCentresInputSchema = CivicDirectoryBaseSchema;

export const PaResidentNetworkCentresSchema = requireLatLngPair(PaResidentNetworkCentresInputSchema);

export const SportSgFacilitiesInputSchema = CivicDirectoryBaseSchema.extend({
  facilityType: z.string().min(1).optional(),
});

export const SportSgFacilitiesSchema = requireLatLngPair(SportSgFacilitiesInputSchema);

export const EcdaChildcareCentresInputSchema = CivicDirectoryBaseSchema.extend({
  centreType: z.string().min(1).optional(),
  operatorType: z.string().min(1).optional(),
  hasVacancy: z.boolean().optional(),
});

export const EcdaChildcareCentresSchema = requireLatLngPair(EcdaChildcareCentresInputSchema);

export const MsfFamilyServicesInputSchema = CivicDirectoryBaseSchema;

export const MsfFamilyServicesSchema = requireLatLngPair(MsfFamilyServicesInputSchema);

export const MsfStudentCareServicesInputSchema = CivicDirectoryBaseSchema.extend({
  auditStatus: z.string().min(1).optional(),
  scfaOnly: z.boolean().optional(),
});

export const MsfStudentCareServicesSchema = requireLatLngPair(MsfStudentCareServicesInputSchema);

export const MsfSocialServiceOfficesInputSchema = CivicDirectoryBaseSchema;

export const MsfSocialServiceOfficesSchema = requireLatLngPair(MsfSocialServiceOfficesInputSchema);

export const HawkerCentresInputSchema = z.object({
  name: z.string().min(1).optional(),
  lat: z.number().min(-90).max(90).optional(),
  lng: z.number().min(-180).max(180).optional(),
  radiusKm: z.number().positive().max(20).optional(),
  limit: z.number().int().positive().max(200).optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
}).strict();

export const HawkerCentresSchema = requireLatLngPair(HawkerCentresInputSchema);

export const MoeSchoolsSchema = z.object({
  level: z.string().min(1).optional(),
  zone: z.string().min(1).optional(),
  name: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const MohFacilitiesSchema = z.object({
  type: z.string().min(1).optional(),
  name: z.string().min(1).optional(),
  postalCode: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const SfaEstablishmentsSchema = z.object({
  name: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const NParksSchema = z.object({
  name: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const PubWaterLevelsSchema = z.object({
  station: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const MomLabourStatsSchema = z.object({
  indicator: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const StbVisitorStatsSchema = z.object({
  country: z.string().min(1).optional(),
  year: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const LtaCarparkAvailabilitySchema = z.object({
  carparkId: z.string().min(1).optional(),
  development: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
}).strict();

export const LtaTaxiAvailabilitySchema = z.object({
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
}).strict();

export const LtaCoeResultsSchema = z.object({
  category: z.string().min(1).optional(),
  biddingNo: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const IrasTaxCollectionSchema = z.object({
  financialYear: z.string().min(1).optional(),
  taxType: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const SpfCrimeStatsSchema = z.object({
  offenceCategory: z.string().min(1).optional(),
  year: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const EmaElectricityGenerationSchema = z.object({
  energyType: z.string().min(1).optional(),
  year: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const VisualizeInputSchema = z.object({
  values: z.array(z.number().finite()).min(2).optional(),
  labels: z.array(z.string()).optional(),
  tableId: z.string().min(1).optional(),
  indicator: z.string().min(1).optional(),
  startYear: z.number().int().optional(),
  endYear: z.number().int().optional(),
  width: z.number().int().min(10).max(120).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const VisualizeSchema = VisualizeInputSchema.refine(
  (data) => data.values !== undefined || (data.tableId !== undefined && data.indicator !== undefined),
  { message: "Provide either values[] or (tableId + indicator) to visualize." },
);

export const NlbLibrariesSchema = z.object({
  name: z.string().min(1).optional(),
  region: z.string().min(1).optional(),
  postalCode: z.string().min(1).optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv", "geojson"]).optional(),
}).strict();

export const HawkerClosuresSchema = z.object({
  centre: z.string().min(1).optional(),
  startDate: IsoDateSchema.optional(),
  endDate: IsoDateSchema.optional(),
  limit: z.number().int().positive().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const LawSearchSchema = z.object({
  query: z.string().min(2),
  limit: z.number().int().positive().max(50).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const CrossDatasetSchema = z.object({
  leftTableId: z.string().min(1),
  leftIndicator: z.string().min(1),
  leftLabel: z.string().min(1),
  rightTableId: z.string().min(1),
  rightIndicator: z.string().min(1),
  rightLabel: z.string().min(1),
  startYear: z.number().int().optional(),
  endYear: z.number().int().optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

const GovFeedIdSchema = z.enum([
  "nea_news_updates",
  "nea_tender_notices",
  "nea_upcoming_events",
  "weather_2hr_forecast",
  "weather_24hr_forecast",
  "weather_4day_forecast",
  "weather_heavy_rain",
  "weather_cap_alert",
  "weather_portal_updates",
  "sfa_newsroom",
  "sfa_media_releases",
  "sfa_food_alerts",
  "sfa_circulars",
  "mpa_media_releases",
  "mpa_press_releases",
  "nhb_general",
  "nhb_exhibitions",
  "nhb_programmes",
  "nhb_publications",
  "nhb_trails",
  "ura_media_releases",
  "ura_speeches",
  "ura_announcements",
  "ura_news",
  "ura_publications",
]);

export const GovFeedCatalogSchema = z.object({
  family: z.enum(["all", "nea", "weather", "sfa", "mpa", "nhb", "ura"]).optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const GovFeedItemsSchema = z.object({
  feedId: GovFeedIdSchema,
  limit: z.number().int().positive().max(100).optional(),
  keyword: z.string().min(1).optional(),
  format: z.enum(["json", "markdown", "csv"]).optional(),
}).strict();

export const QuerySchema = z.object({
  query: z.string().min(1),
  format: OutputFormatSchema.optional(),
  mode: z.enum(["execute", "plan"]).optional(),
  includeContextIds: z.boolean().optional(),
}).strict();

const QueryContextIdsSchema = ContextIdsSchema;

export const QueryPlannedResultSchema = z.object({
  status: z.literal("planned"),
  mode: z.literal("plan"),
  workflow: z.string().min(1),
  intent: z.string().min(1),
  apis: z.array(z.string().min(1)),
  confidence: z.number().min(0).max(1),
  toolsUsed: z.array(z.string().min(1)),
  steps: z.array(QueryPlannedStepSchema),
  contextIds: QueryContextIdsSchema.optional(),
}).strict();

export const QueryCompletedResultSchema = z.object({
  status: z.literal("completed"),
  mode: z.literal("execute"),
  workflow: z.string().min(1),
  intent: z.string().min(1),
  apis: z.array(z.string().min(1)),
  confidence: z.number().min(0).max(1),
  toolsUsed: z.array(z.string().min(1)),
  steps: z.array(QueryExecutedStepSchema),
  routingExplanation: z.string().min(1),
  continuationHints: z.array(z.string().min(1)).optional(),
  resultSummary: QueryResultSummarySchema.optional(),
  nextActions: z.array(NextCheckSchema).optional(),
  contextIds: QueryContextIdsSchema.optional(),
}).strict();

export const QueryBlockedResultSchema = z.object({
  status: z.literal("blocked"),
  mode: z.enum(["execute", "plan"]),
  workflow: z.string().min(1),
  intent: z.string().min(1),
  apis: z.array(z.string().min(1)),
  confidence: z.number().min(0).max(1),
  toolsUsed: z.array(z.string().min(1)),
  steps: z.array(QueryPlannedStepSchema),
  blockers: z.array(QueryBlockerSchema).min(1),
  reason: z.string().min(1),
  suggestion: z.string().min(1),
  routingExplanation: z.string().min(1),
  contextIds: QueryContextIdsSchema.optional(),
}).strict();

export const QueryUnsupportedResultSchema = z.object({
  status: z.literal("unsupported"),
  mode: z.enum(["execute", "plan"]),
  reason: z.string().min(1),
  suggestion: z.string().min(1),
  workflow: z.string().min(1).optional(),
  intent: z.string().min(1).optional(),
  apis: z.array(z.string().min(1)).optional(),
  confidence: z.number().min(0).max(1).optional(),
  toolsUsed: z.array(z.string().min(1)).optional(),
  steps: z.array(QueryPlannedStepSchema).optional(),
  contextIds: QueryContextIdsSchema.optional(),
}).strict();

export const QueryFailedResultSchema = z.object({
  status: z.literal("failed"),
  mode: z.literal("execute"),
  workflow: z.string().min(1),
  intent: z.string().min(1),
  apis: z.array(z.string().min(1)),
  confidence: z.number().min(0).max(1),
  toolsUsed: z.array(z.string().min(1)),
  steps: z.array(QueryExecutedStepSchema),
  routingExplanation: z.string().min(1),
  resultSummary: QueryResultSummarySchema.optional(),
  nextActions: z.array(NextCheckSchema).optional(),
  failedStep: QueryExecutedStepSchema.nullable(),
  contextIds: QueryContextIdsSchema.optional(),
}).strict();

export const QueryOutcomeSchema = z.discriminatedUnion("status", [
  QueryPlannedResultSchema,
  QueryCompletedResultSchema,
  QueryBlockedResultSchema,
  QueryUnsupportedResultSchema,
  QueryFailedResultSchema,
]);

const HousingApplicantSchema = z.object({
  age: z.number().int().positive(),
  citizenship: z.enum(["citizen", "pr", "foreigner"]),
  monthlyIncomeSgd: z.number().nonnegative(),
  employmentMonths: z.number().int().nonnegative().optional(),
  firstTimer: z.boolean().optional(),
}).strict();

const HouseholdProfileSchema = z.object({
  applicants: z.array(HousingApplicantSchema).min(1).max(4),
  maritalStatus: z.enum(["single", "married", "joint_singles", "fiance_fiancee"]),
  flatMode: z.enum(["bto", "resale"]),
  flatSize: z.enum(["2_room", "3_room", "4_room", "5_room", "executive"]),
  proximityToParents: z.enum(["live_with", "near", "neither"]).optional(),
  upgradingFromTwoRoomBtoNonMature: z.boolean().optional(),
}).strict();

export const HousingGrantEligibilitySchema = z.object({
  profile: HouseholdProfileSchema,
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

const BankPackageSchema = z.object({
  bank: z.string().min(1),
  packageName: z.string().min(1),
  rateBasis: z.enum(["sora_1m", "sora_3m", "fixed", "board_rate"]),
  spreadBps: z.number().optional(),
  fixedRate: z.number().optional(),
  lockInYears: z.number().int().nonnegative().optional(),
  thereafterSpreadBps: z.number().optional(),
  notes: z.string().optional(),
}).strict();

export const HousingLoanCompareSchema = z.object({
  priceSgd: z.number().positive(),
  downpaymentSgd: z.number().nonnegative(),
  tenureYears: z.number().int().positive().max(35),
  soraValue: z.number().nonnegative().optional(),
  soraTenor: z.enum(["1m", "3m"]).optional(),
  bankPackages: z.array(BankPackageSchema).max(20).optional(),
  includeHdbLoan: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const HousingAffordabilitySchema = z.object({
  profile: HouseholdProfileSchema,
  targetPriceSgd: z.number().positive(),
  tenureYears: z.number().int().positive().max(35),
  cashOnHandSgd: z.number().nonnegative(),
  cpfOaBalanceSgd: z.number().nonnegative(),
  otherMonthlyDebtSgd: z.number().nonnegative().optional(),
  soraValue: z.number().nonnegative().optional(),
  bankPackages: z.array(BankPackageSchema).max(20).optional(),
  loanType: z.enum(["hdb", "bank"]).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const HousingResaleCompareSchema = z.object({
  town: z.string().min(1),
  flatType: z.string().min(1),
  askingPriceSgd: z.number().positive(),
  storeyBand: z.string().min(1).optional(),
  remainingLeaseYears: z.number().int().positive().max(99).optional(),
  lookbackMonths: z.number().int().positive().max(36).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

export const validateInput = <T>(schema: ZodSchema<T>, input: unknown): T => {
  const result = schema.safeParse(input);
  if (!result.success) {
    throw new ValidationError(
      `Invalid input: ${result.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join(", ")}`,
      result.error.issues,
    );
  }
  return result.data;
};
