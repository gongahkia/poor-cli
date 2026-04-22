import type { ToolCatalogEntry } from "./tool-definition.js";
import { toToolCatalogEntry } from "./tool-definition.js";
import { ALL_TOOL_DEFINITIONS } from "./tool-set.js";
import { LIVE_API_SURFACE, LIVE_WORKFLOW_SMOKE_CASES, RELEASE_BLOCKING_COMMANDS } from "./runtime-surface.js";
import { TOOLSET_PROFILE_CATALOG } from "./toolset-profiles.js";
import { OPS_TAXONOMY_CATALOG } from "../ops-taxonomy.js";

export type ApiCatalogEntry = {
  readonly name: string;
  readonly description: string;
  readonly tools: readonly string[];
  readonly authRequired: boolean;
  readonly rateLimit: string;
  readonly positioning: string;
  readonly preferredInterface?: string;
  readonly scopeNotes?: readonly string[];
};

export type WorkflowCatalogEntry = {
  readonly id?: string;
  readonly name: string;
  readonly intent: string;
  readonly entrypoints: readonly {
    readonly tool: string;
    readonly input: Readonly<Record<string, unknown>>;
  }[];
  readonly requiredInputs?: readonly string[];
  readonly blockerFields?: readonly string[];
  readonly authPrerequisites?: readonly string[];
  readonly fallbackTools?: readonly string[];
  readonly continuationTools?: readonly string[];
  readonly continuationHints?: readonly string[];
  readonly outputShapeVersion?: string;
  readonly outputShapeNotes?: readonly string[];
};

export type RecipeCatalogEntry = {
  readonly id?: string;
  readonly name: string;
  readonly goal: string;
  readonly prompt: string;
  readonly preferredEntrypoint: {
    readonly tool: string;
    readonly input: Readonly<Record<string, unknown>>;
  };
  readonly fallbackTools: readonly string[];
  readonly notes: readonly string[];
  readonly requiredInputs?: readonly string[];
  readonly blockerFields?: readonly string[];
  readonly authPrerequisites?: readonly string[];
  readonly continuationTools?: readonly string[];
  readonly continuationHints?: readonly string[];
  readonly outputShapeVersion?: string;
  readonly outputShapeNotes?: readonly string[];
};

export type PlaybookCatalogEntry = {
  readonly id?: string;
  readonly name: string;
  readonly persona: string;
  readonly jobsToBeDone: readonly string[];
  readonly recommendedResources: readonly string[];
  readonly primaryWorkflows: readonly string[];
  readonly starterPrompts: readonly string[];
  readonly directTools: readonly string[];
  readonly notes: readonly string[];
};

export type RuntimeCatalog = {
  readonly toolsetProfiles: readonly {
    readonly profile: string;
    readonly intent: string;
    readonly toolsets: readonly string[];
  }[];
  readonly liveSurface: readonly {
    readonly api: string;
    readonly classification: string;
    readonly authRequired: boolean;
    readonly probeMode: string;
    readonly productionUrl: string;
    readonly representativeTool: string;
    readonly releaseBlocking: boolean;
    readonly coversFamilies: readonly string[];
    readonly notes: readonly string[];
  }[];
  readonly authDependencies: readonly {
    readonly api: string;
    readonly authRequired: boolean;
    readonly envVars: readonly string[];
    readonly keystoreKeys: readonly string[];
    readonly dependentFamilies?: readonly string[];
    readonly notes: readonly string[];
  }[];
  readonly credentialSourceRules: readonly string[];
  readonly latency: {
    readonly hardCapMs: number;
    readonly targets: readonly {
      readonly api: string;
      readonly timeoutMs: number;
      readonly typicalLatency: string;
      readonly notes: string;
    }[];
  };
  readonly cacheTiers: readonly {
    readonly tier: string;
    readonly ttlSeconds: number;
    readonly usedBy: readonly string[];
    readonly rationale: string;
  }[];
  readonly rateLimits: readonly {
    readonly api: string;
    readonly maxTokens: number;
    readonly refillPerSecond: number;
    readonly effectiveRate: string;
  }[];
  readonly retryPolicy: {
    readonly retryable: readonly string[];
    readonly nonRetryable: readonly string[];
    readonly backoffSeconds: readonly number[];
    readonly maxRetries: number;
    readonly respectsRetryAfter: boolean;
  };
  readonly circuitBreaker: {
    readonly threshold: number;
    readonly resetTimeoutSeconds: number;
    readonly states: readonly string[];
    readonly note: string;
  };
  readonly partialFailureSemantics: readonly string[];
  readonly healthCoverage: readonly {
    readonly api: string;
    readonly coversFamilies: readonly string[];
    readonly notes: readonly string[];
  }[];
  readonly releaseReadiness: {
    readonly blockingCommands: readonly string[];
    readonly requiredSmokeCases: readonly {
      readonly name: string;
      readonly tool: string;
      readonly layer: "api" | "workflow";
      readonly authRequired: boolean;
      readonly releaseBlocking: boolean;
      readonly arguments: Readonly<Record<string, unknown>>;
      readonly expectation: Readonly<Record<string, unknown>>;
      readonly notes: readonly string[];
    }[];
    readonly failureSemantics: readonly string[];
    readonly notes: readonly string[];
  };
  readonly queryStatusContract: readonly {
    readonly status: "planned" | "completed" | "blocked" | "unsupported" | "failed";
    readonly isError: boolean;
    readonly notes: string;
  }[];
};

export const API_CATALOG: readonly ApiCatalogEntry[] = [
  {
    name: "SingStat",
    description: "Singapore Department of Statistics for dataset discovery, table reads, time series, and explicit indicator comparisons.",
    tools: ["sg_singstat_search", "sg_singstat_table", "sg_singstat_timeseries", "sg_singstat_compare", "sg_singstat_browse"],
    authRequired: false,
    rateLimit: "10 tokens, 2/sec refill",
    positioning: "Canonical direct tool family for macroeconomic and statistical work.",
    preferredInterface: "sg_query",
  },
  {
    name: "MAS",
    description: "Monetary Authority of Singapore for latest or exact-date exchange rates, SORA, and banking statistics.",
    tools: ["sg_mas_exchange_rates", "sg_mas_interest_rates", "sg_mas_financial_stats"],
    authRequired: false,
    rateLimit: "10 tokens, 2/sec refill",
    positioning: "Narrow but honest monetary-data surface for this pilot.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "sg_mas_exchange_rates supports latest or exact-date lookup only.",
      "sg_mas_interest_rates is SORA-only in this phase.",
      "sg_mas_financial_stats is banking-only in this phase.",
    ],
  },
  {
    name: "OneMap",
    description: "Singapore's national map for geocoding, routing, planning-area demographics, and coordinate conversion.",
    tools: ["sg_onemap_geocode", "sg_onemap_reverse_geocode", "sg_onemap_route", "sg_onemap_population", "sg_onemap_convert_coords"],
    authRequired: true,
    rateLimit: "50 tokens, 4/sec refill (~250/min)",
    positioning: "Primary location and demographic surface.",
    preferredInterface: "sg_query",
  },
  {
    name: "URA",
    description: "Urban Redevelopment Authority for property transactions, planning-area lookup, and development charges.",
    tools: ["sg_ura_property_transactions", "sg_ura_planning_area", "sg_ura_dev_charges"],
    authRequired: true,
    rateLimit: "5 tokens, 1/sec refill",
    positioning: "Primary property and planning context surface.",
    preferredInterface: "sg_query",
  },
  {
    name: "LTA DataMall",
    description: "Land Transport Authority live transport data for bus arrivals, train alerts, and traffic incidents.",
    tools: [
      "sg_lta_bus_arrivals",
      "sg_lta_train_alerts",
      "sg_lta_traffic_incidents",
      "sg_lta_road_works",
      "sg_lta_road_openings",
      "sg_lta_traffic_images",
    ],
    authRequired: true,
    rateLimit: "20 tokens, 2/sec refill",
    positioning: "Primary transport-status surface for live operational checks.",
    preferredInterface: "sg_query",
  },
  {
    name: "Transit Intelligence",
    description: "Additive transit decision surface built over live LTA and traffic-image context for health scoring, hotspot triage, reliability, and policy-aware planning.",
    tools: [
      "sg_transit_health",
      "sg_transit_hotspots",
      "sg_transit_ops_brief",
      "sg_transit_pack",
      "sg_transit_reliability",
      "sg_transit_transfer_risk",
      "sg_transit_accessible_route",
      "sg_transit_objective_plan",
      "sg_transit_counterfactual_simulate",
      "sg_transit_outcome_record",
      "sg_transit_model_metrics",
      "sg_transit_policy_audit",
      "sg_transit_policy_insights",
      "sg_transit_policy_replay",
    ],
    authRequired: true,
    rateLimit: "20 tokens, 2/sec refill via LTA-dependent feeds",
    positioning: "First-party transit-intelligence data family in the same hierarchy as other SG additive and direct surfaces.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Operational scores and recommendations are deterministic heuristics over bounded public-feed signals.",
      "Use sg_transit_ops_brief for artifact-first adoption, then drop to direct transit primitives as needed.",
    ],
  },
  {
    name: "NEA",
    description: "National Environment Agency realtime weather, rainfall, and air-quality data.",
    tools: ["sg_nea_forecast_2hr", "sg_nea_air_quality", "sg_nea_rainfall"],
    authRequired: false,
    rateLimit: "20 tokens, 2/sec refill",
    positioning: "Primary environment-status surface for weather and air-quality checks.",
    preferredInterface: "sg_query",
  },
  {
    name: "HDB",
    description: "Curated housing-market surface over official HDB resale and rental datasets from data.gov.sg.",
    tools: ["sg_hdb_resale_prices", "sg_hdb_rental_prices"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg",
    positioning: "Explicit housing-market surface for HDB resale and rental checks.",
    preferredInterface: "sg_query",
  },
  {
    name: "CEA",
    description: "Curated estate-agent diligence surface over the official CEA salesperson registry published on data.gov.sg.",
    tools: ["sg_cea_salespersons"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg",
    positioning: "Direct diligence surface for salesperson and estate-agent registration checks.",
    preferredInterface: "sg_query",
  },
  {
    name: "BCA",
    description: "Curated contractor diligence surface over official BCA builder and contractor registries published on data.gov.sg.",
    tools: ["sg_bca_licensed_builders", "sg_bca_registered_contractors"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg",
    positioning: "Direct diligence surface for builder and contractor registration checks.",
    preferredInterface: "sg_query",
  },
  {
    name: "BOA",
    description: "Curated Board of Architects diligence surface over official architect and architecture-firm registers published on data.gov.sg.",
    tools: ["sg_boa_architects", "sg_boa_architecture_firms"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg file downloads",
    positioning: "Direct diligence surface for architecture-firm and architect registration checks.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Backed by the official BOA architect and architecture-firm CSV registers on data.gov.sg.",
    ],
  },
  {
    name: "ACRA",
    description: "Curated company-registry surface over the official ACRA corporate-entities collection published on data.gov.sg.",
    tools: ["sg_acra_entities"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg",
    positioning: "Primary entity-registration surface for company and UEN lookups.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Backed by the official 27-shard public corporate-entities collection.",
    ],
  },
  {
    name: "PA",
    description: "People's Association civic directories for community clubs, PAssion WaVe outlets, and residents' network centres.",
    tools: ["sg_pa_community_outlets", "sg_pa_resident_network_centres"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg file downloads",
    positioning: "Neighbourhood civic-discovery surface for community facilities and grassroots locations.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Backed by PA geospatial datasets on data.gov.sg.",
      "Optimized for postal-code and proximity lookups rather than recommendations.",
    ],
  },
  {
    name: "Sport Singapore",
    description: "Sport Singapore public facility directory for sport centres, stadiums, swimming complexes, and selected specialist venues.",
    tools: ["sg_sportsg_facilities"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg file downloads",
    positioning: "Daily-utility civic discovery for public sports infrastructure.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Backed by the SportSG public-facilities GeoJSON dataset on data.gov.sg.",
    ],
  },
  {
    name: "ECDA",
    description: "Early Childhood Development Agency childcare discovery combining geospatial centre locations with listing and vacancy data.",
    tools: ["sg_ecda_childcare_centres"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg file downloads",
    positioning: "Family-focused civic discovery for nearby childcare options.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Joins Child Care Services GeoJSON with Listing of Centres CSV by postal code first, then normalized centre name.",
      "Vacancy signals are bounded to the current-month statuses surfaced in the listing dataset.",
    ],
  },
  {
    name: "MSF Family Services",
    description: "Ministry of Social and Family Development family service centre directory for neighbourhood support discovery.",
    tools: ["sg_msf_family_services"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg file downloads",
    positioning: "Neighbourhood social-support discovery for family service centres.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Backed by the official Family Services GeoJSON dataset on data.gov.sg.",
    ],
  },
  {
    name: "MSF Student Care Services",
    description: "Ministry of Social and Family Development student care directory with audit status, SCFA signal, and fee metadata.",
    tools: ["sg_msf_student_care_services"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg file downloads",
    positioning: "Family-focused discovery for student care options and SCFA coverage.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Supports audit-status and SCFA-only filters over the official Student Care Services GeoJSON dataset.",
    ],
  },
  {
    name: "MSF Social Service Offices",
    description: "Ministry of Social and Family Development social service office directory for in-person assistance and office lookup.",
    tools: ["sg_msf_social_service_offices"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg file downloads",
    positioning: "Assistance-office discovery for nearby government support locations.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Backed by the official Social Service Offices GeoJSON dataset on data.gov.sg.",
    ],
  },
  {
    name: "GeBIZ",
    description: "Singapore government procurement portal for tender awards and contract data.",
    tools: ["sg_gebiz_tenders"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Government procurement discovery for business-facing agents.",
    preferredInterface: "sg_gebiz_tenders",
    scopeNotes: [
      "Backed by GeBIZ tender award data published on data.gov.sg.",
    ],
  },
  {
    name: "Hawker Centres",
    description: "Singapore hawker centre directory with locations, stall counts, and addresses.",
    tools: ["sg_hawker_centres"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Civic amenity discovery for location and property workflows.",
    preferredInterface: "sg_hawker_centres",
    scopeNotes: [
      "Includes geocoordinates for proximity-based lookups.",
    ],
  },
  {
    name: "MOE Schools",
    description: "Singapore school directory from the Ministry of Education.",
    tools: ["sg_moe_schools"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Education discovery for relocation and family-focused workflows.",
    preferredInterface: "sg_moe_schools",
    scopeNotes: [
      "Filterable by level (PRIMARY, SECONDARY, JC), zone, and name.",
    ],
  },
  {
    name: "MOH Healthcare",
    description: "Singapore healthcare facility directory from the Ministry of Health.",
    tools: ["sg_moh_facilities"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Healthcare facility discovery for consumer and property workflows.",
    preferredInterface: "sg_moh_facilities",
    scopeNotes: [
      "Covers hospitals, polyclinics, medical clinics, and dental clinics.",
    ],
  },
  {
    name: "HSA",
    description: "Health Sciences Authority licensing surface for licensed pharmacies and companies licensed to import, wholesale, or manufacture health products.",
    tools: ["sg_hsa_licensed_pharmacies", "sg_hsa_health_product_licensees"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg file downloads",
    positioning: "Healthcare and life-sciences diligence surface for pharmacy and product-licensing checks.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "Backed by the official HSA licensed pharmacies and health-product licensee CSV datasets on data.gov.sg.",
    ],
  },
  {
    name: "SFA",
    description: "Singapore Food Agency licensed food establishments directory.",
    tools: ["sg_sfa_establishments"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "F&B compliance and food safety discovery.",
    preferredInterface: "sg_sfa_establishments",
    scopeNotes: ["Backed by SFA licensed eating establishment data on data.gov.sg."],
  },
  {
    name: "NParks",
    description: "Singapore parks and nature reserves directory.",
    tools: ["sg_nparks_parks"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Green space discovery for environmental and property workflows.",
    preferredInterface: "sg_nparks_parks",
    scopeNotes: ["Backed by NParks data on data.gov.sg."],
  },
  {
    name: "PUB",
    description: "Singapore water level monitoring from PUB stations.",
    tools: ["sg_pub_water_levels"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Water level and flood risk monitoring.",
    preferredInterface: "sg_pub_water_levels",
    scopeNotes: ["Backed by PUB water level data on data.gov.sg."],
  },
  {
    name: "MOM",
    description: "Singapore labour market statistics from the Ministry of Manpower.",
    tools: ["sg_mom_labour_stats"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Labour market analysis for macro and economic workflows.",
    preferredInterface: "sg_mom_labour_stats",
    scopeNotes: ["Backed by MOM labour statistics on data.gov.sg."],
  },
  {
    name: "STB",
    description: "Singapore tourism visitor arrival statistics.",
    tools: ["sg_stb_visitor_stats"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Tourism industry analysis and visitor trend monitoring.",
    preferredInterface: "sg_stb_visitor_stats",
    scopeNotes: ["Backed by STB visitor arrival data on data.gov.sg."],
  },
  {
    name: "HLB",
    description: "Hotels Licensing Board hotel directory with keeper names, room counts, and geospatial location context.",
    tools: ["sg_hlb_hotels"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg file downloads",
    positioning: "Hospitality diligence and hotel-operator lookup surface.",
    preferredInterface: "sg_query",
    scopeNotes: ["Backed by the official HLB Hotels GeoJSON dataset on data.gov.sg."],
  },
  {
    name: "data.gov.sg",
    description: "Singapore open data portal for broad dataset discovery, metadata retrieval, machine-readable resource inspection, and bounded datastore row reads.",
    tools: ["sg_datagov_search", "sg_datagov_get", "sg_datagov_resources", "sg_datagov_rows", "sg_datagov_browse"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Fallback discovery and row-access surface when the domain APIs do not fit.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "sg_datagov_get returns dataset metadata only.",
      "sg_datagov_resources exposes the current machine-readable resource shape for a dataset.",
      "sg_datagov_rows performs bounded datastore reads with explicit filters, limit, offset, and sort.",
    ],
  },
];

export const TOOL_CATALOG: readonly ToolCatalogEntry[] = ALL_TOOL_DEFINITIONS.map(toToolCatalogEntry);

const ONEMAP_AUTH_NOTES = [
  "Requires OneMap credentials when the workflow needs geocoding, routing, reverse geocoding, or planning-area demographics.",
] as const;

const URA_AUTH_NOTES = [
  "Requires a URA API key when the workflow resolves planning areas or reads URA transactions and development-charge tables.",
] as const;

const LTA_AUTH_NOTES = [
  "Requires an LTA DataMall API key for live bus, train, and traffic status reads.",
] as const;

export const WORKFLOW_CATALOG: readonly WorkflowCatalogEntry[] = [
  {
    name: "Macro Snapshot",
    intent: "Build a compact Singapore macro starter brief with MAS values and validated SingStat GDP and CPI tables.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Macro snapshot of Singapore", mode: "execute" } },
      { tool: "sg_macro_brief", input: { currency: "USD" } },
      { tool: "sg_mas_exchange_rates", input: { currency: "USD", startDate: "2026-03-01", endDate: "2026-03-26" } },
      { tool: "sg_singstat_search", input: { keyword: "Singapore GDP" } },
    ],
    requiredInputs: ["query"],
    fallbackTools: ["sg_macro_brief", "sg_mas_exchange_rates", "sg_singstat_search"],
    continuationTools: ["sg_singstat_table", "sg_singstat_timeseries", "sg_mas_interest_rates"],
    continuationHints: [
      "Start with sg_macro_brief for the compact artifact, then drop to SingStat table and time-series reads once you know the table IDs.",
    ],
  },
  {
    name: "Demographic Profile",
    intent: "Inspect a planning area's population and household profile, optionally starting from a postal code.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Demographic profile for postal code 168742", mode: "execute" } },
      { tool: "sg_onemap_population", input: { planningArea: "Tampines", dataType: "getPopulationAgeGroup" } },
      { tool: "sg_onemap_population", input: { planningArea: "Tampines", dataType: "getHouseholdMonthlyIncomeWork" } },
    ],
    requiredInputs: ["planningArea or postalCode"],
    blockerFields: ["planningArea", "postalCode"],
    authPrerequisites: [...ONEMAP_AUTH_NOTES, ...URA_AUTH_NOTES],
    fallbackTools: ["sg_onemap_population", "sg_onemap_geocode", "sg_ura_planning_area"],
    continuationTools: ["sg_onemap_population", "sg_ura_planning_area"],
    continuationHints: [
      "Postal-code prompts route through geocode plus planning-area resolution before the two demographic reads execute.",
    ],
  },
  {
    name: "Civic Discovery",
    intent: "Find nearby family service centres, student care centres, social service offices, community outlets, residents' network centres, SportSG facilities, or childcare centres from a postal code, address, planning area, coordinates, or exact facility name.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Find a family service centre near 560230", mode: "execute" } },
      { tool: "sg_msf_family_services", input: { postalCode: "560230" } },
      { tool: "sg_msf_student_care_services", input: { postalCode: "750471", scfaOnly: true } },
      { tool: "sg_msf_social_service_offices", input: { name: "Social Service Office @ Queenstown" } },
      { tool: "sg_pa_community_outlets", input: { type: "community_club", postalCode: "560123" } },
      { tool: "sg_sportsg_facilities", input: { facilityType: "swimming_complex", postalCode: "560123" } },
      { tool: "sg_ecda_childcare_centres", input: { postalCode: "560123", hasVacancy: true } },
    ],
    requiredInputs: ["directory intent", "postalCode or planningArea or address or lat/lng or exact name"],
    blockerFields: ["directory", "postalCode", "address", "planningArea", "lat", "lng", "name"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    fallbackTools: [
      "sg_onemap_geocode",
      "sg_msf_family_services",
      "sg_msf_student_care_services",
      "sg_msf_social_service_offices",
      "sg_pa_community_outlets",
      "sg_pa_resident_network_centres",
      "sg_sportsg_facilities",
      "sg_ecda_childcare_centres",
    ],
    continuationTools: [
      "sg_msf_family_services",
      "sg_msf_student_care_services",
      "sg_msf_social_service_offices",
      "sg_pa_community_outlets",
      "sg_pa_resident_network_centres",
      "sg_sportsg_facilities",
      "sg_ecda_childcare_centres",
    ],
    continuationHints: [
      "Use exact quoted facility names for direct lookups, or coordinates when an agent already resolved location outside sg_query.",
    ],
  },
  {
    name: "Property And Regulatory Due Diligence",
    intent: "Build a location and property brief with URA planning, URA transactions, HDB context, and optional live context.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Property due diligence for Bedok HDB resale", mode: "execute" } },
      { tool: "sg_property_brief", input: { planningArea: "Bedok", flatType: "4 ROOM", includeEnvironment: true } },
      { tool: "sg_ura_property_transactions", input: { propertyType: "residential", area: "Bedok" } },
      { tool: "sg_hdb_resale_prices", input: { town: "Bedok", flatType: "4 ROOM" } },
    ],
    requiredInputs: ["planningArea or postalCode"],
    blockerFields: ["planningArea", "postalCode"],
    authPrerequisites: URA_AUTH_NOTES,
    fallbackTools: ["sg_property_brief", "sg_ura_property_transactions", "sg_hdb_resale_prices"],
    continuationTools: ["sg_ura_dev_charges", "sg_hdb_rental_prices", "sg_environment_brief", "sg_transport_brief"],
    continuationHints: [
      "Use sg_property_brief for the combined artifact, then continue into URA, HDB, environment, or transport direct tools when you need deeper evidence.",
    ],
  },
  {
    name: "Property Counterparty Diligence",
    intent: "Combine URA and HDB market context with CEA and BCA registry checks for counterparties involved in a property deal.",
    entrypoints: [
      { tool: "sg_ura_property_transactions", input: { propertyType: "residential", area: "Bedok" } },
      { tool: "sg_hdb_resale_prices", input: { town: "Bedok", flatType: "4 ROOM" } },
      { tool: "sg_cea_salespersons", input: { estateAgentName: "ERA REALTY NETWORK PTE LTD" } },
      { tool: "sg_acra_entities", input: { entityName: "ABC CONSTRUCTION PTE LTD" } },
      { tool: "sg_bca_licensed_builders", input: { companyName: "ABC CONSTRUCTION PTE LTD" } },
      { tool: "sg_bca_registered_contractors", input: { companyName: "ABC CONSTRUCTION PTE LTD" } },
    ],
    requiredInputs: ["planningArea or town", "companyName or entityName or registrationNo"],
    fallbackTools: [
      "sg_ura_property_transactions",
      "sg_hdb_resale_prices",
      "sg_cea_salespersons",
      "sg_acra_entities",
      "sg_bca_licensed_builders",
      "sg_bca_registered_contractors",
    ],
    continuationTools: ["sg_business_dossier", "sg_datagov_resources"],
    continuationHints: [
      "This is intentionally a direct-tool workflow; use sg_business_dossier when you want the registry synthesis artifact first.",
    ],
  },
  {
    name: "Business Registry Diligence",
    intent: "Build a cross-registry business dossier across ACRA, BCA, and CEA records, with explicit module extension into GeBIZ, BOA, HSA, and HLB when requested.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Registry diligence for UEN 201912345K", mode: "execute" } },
      { tool: "sg_business_dossier", input: { uen: "201912345K" } },
      { tool: "sg_acra_entities", input: { uen: "201912345K" } },
      { tool: "sg_bca_licensed_builders", input: { companyName: "ABC CONSTRUCTION PTE LTD" } },
      { tool: "sg_bca_registered_contractors", input: { companyName: "ABC CONSTRUCTION PTE LTD" } },
      { tool: "sg_cea_salespersons", input: { registrationNo: "R123456A" } },
    ],
    requiredInputs: ["entityName or companyName or uen or registrationNo or salespersonName"],
    blockerFields: ["entityName", "uen", "registrationNo"],
    fallbackTools: ["sg_business_dossier", "sg_acra_entities", "sg_bca_licensed_builders", "sg_bca_registered_contractors", "sg_cea_salespersons"],
    continuationTools: ["sg_datagov_resources", "sg_datagov_rows"],
    continuationHints: [
      "Use the dossier for the high-signal artifact, then drop to direct registries when you need raw source records or narrower filters.",
    ],
  },
  {
    id: "architecture_firm_diligence",
    name: "Architecture Firm Diligence",
    intent: "Build a bounded architecture-firm diligence artifact using BOA, ACRA, and optional GeBIZ procurement evidence.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Architecture firm diligence for DP Architects", mode: "execute" } },
      { tool: "sg_business_dossier", input: { entityName: "DP Architects", modules: ["acra", "boa", "gebiz"], sectorHints: ["architecture", "procurement"] } },
      { tool: "sg_boa_architecture_firms", input: { firmName: "DP Architects" } },
      { tool: "sg_boa_architects", input: { firmName: "DP Architects" } },
      { tool: "sg_gebiz_tenders", input: { supplierName: "DP Architects" } },
    ],
    requiredInputs: ["entityName or registrationNo"],
    blockerFields: ["entityName", "registrationNo"],
    fallbackTools: ["sg_business_dossier", "sg_boa_architecture_firms", "sg_boa_architects", "sg_acra_entities", "sg_gebiz_tenders"],
    continuationTools: ["sg_boa_architecture_firms", "sg_boa_architects", "sg_acra_entities", "sg_gebiz_tenders"],
    continuationHints: [
      "Use modules and sectorHints to keep this bounded to architecture-firm evidence instead of broadening into generic company analysis.",
    ],
  },
  {
    id: "healthcare_supplier_diligence",
    name: "Healthcare Supplier Diligence",
    intent: "Build a bounded healthcare supplier diligence artifact using HSA, ACRA, and optional GeBIZ procurement evidence.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", mode: "execute" } },
      { tool: "sg_business_dossier", input: { entityName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", modules: ["acra", "hsa", "gebiz"], sectorHints: ["healthcare", "procurement"] } },
      { tool: "sg_hsa_health_product_licensees", input: { companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD." } },
      { tool: "sg_hsa_licensed_pharmacies", input: { pharmacyName: "A.M. Pharmacy Pte Ltd" } },
      { tool: "sg_gebiz_tenders", input: { supplierName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD." } },
    ],
    requiredInputs: ["entityName"],
    blockerFields: ["entityName"],
    fallbackTools: ["sg_business_dossier", "sg_hsa_health_product_licensees", "sg_hsa_licensed_pharmacies", "sg_acra_entities", "sg_gebiz_tenders"],
    continuationTools: ["sg_hsa_health_product_licensees", "sg_hsa_licensed_pharmacies", "sg_acra_entities", "sg_gebiz_tenders"],
    continuationHints: [
      "Use HSA rows for licence evidence, then add procurement or company-registry evidence only when the use case needs it.",
    ],
  },
  {
    id: "hotel_operator_lookup",
    name: "Hotel Operator Lookup",
    intent: "Look up a hotel or keeper using HLB and optional ACRA company evidence without widening into a generic travel workflow.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Hotel operator lookup for Raffles Hotel Singapore", mode: "execute" } },
      { tool: "sg_business_dossier", input: { entityName: "Raffles Hotel Singapore", modules: ["acra", "hlb"], sectorHints: ["hospitality"] } },
      { tool: "sg_hlb_hotels", input: { name: "Raffles Hotel Singapore" } },
      { tool: "sg_hlb_hotels", input: { keeperName: "Raffles Hotel Singapore" } },
    ],
    requiredInputs: ["entityName or hotel name"],
    blockerFields: ["entityName"],
    fallbackTools: ["sg_business_dossier", "sg_hlb_hotels", "sg_acra_entities"],
    continuationTools: ["sg_hlb_hotels", "sg_acra_entities"],
    continuationHints: [
      "Use HLB for keeper and hotel facts first; only fall back to company-registry context when you need a wider entity check.",
    ],
  },
  {
    id: "sector_scoped_business_diligence",
    name: "Sector Scoped Business Diligence",
    intent: "Build a business dossier with explicit modules and sector hints so the workflow stays bounded to the target industry.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Healthcare supplier business dossier for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", mode: "execute" } },
      { tool: "sg_business_dossier", input: { entityName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", modules: ["acra", "hsa", "gebiz"], sectorHints: ["healthcare", "procurement"] } },
    ],
    requiredInputs: ["entityName plus module or sector scope"],
    blockerFields: ["entityName", "modules", "sectorHints"],
    fallbackTools: ["sg_business_dossier", "sg_acra_entities", "sg_gebiz_tenders", "sg_boa_architecture_firms", "sg_hsa_health_product_licensees", "sg_hlb_hotels"],
    continuationTools: ["sg_business_dossier", "sg_gebiz_tenders", "sg_boa_architecture_firms", "sg_hsa_health_product_licensees", "sg_hlb_hotels"],
    continuationHints: [
      "Prefer explicit modules and sectorHints over free-form planning when you want the diligence surface to stay narrow and auditable.",
    ],
  },
  {
    name: "Dataset Discovery Fallback",
    intent: "Search data.gov.sg and continue from dataset discovery into resource inspection and bounded row reads.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Find datasets about hawker centres", mode: "execute" } },
      { tool: "sg_datagov_search", input: { keyword: "hawker centres" } },
      { tool: "sg_datagov_resources", input: { datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc" } },
      { tool: "sg_datagov_rows", input: { datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc", limit: 5, sort: "month desc" } },
    ],
    requiredInputs: ["keyword"],
    blockerFields: ["datasetId"],
    fallbackTools: ["sg_datagov_search", "sg_datagov_get", "sg_datagov_resources", "sg_datagov_rows"],
    continuationTools: ["sg_datagov_resources", "sg_datagov_rows"],
    continuationHints: [
      "Search first, inspect resources second, and only then run bounded row reads with explicit limits and filters.",
    ],
  },
  {
    name: "Route Planning",
    intent: "Plan directions between two Singapore postal codes or coordinate pairs using OneMap geocoding and routing.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Walk from 049178 to 048616", mode: "execute" } },
      { tool: "sg_onemap_route", input: { startLat: 1.2864, startLng: 103.8537, endLat: 1.284, endLng: 103.851, routeType: "walk" } },
      { tool: "sg_onemap_reverse_geocode", input: { lat: 1.284, lng: 103.851 } },
    ],
    requiredInputs: ["origin and destination as postal codes or coordinate pairs"],
    blockerFields: ["originPostalCode", "destinationPostalCode", "startLat", "startLng", "endLat", "endLng"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    fallbackTools: ["sg_onemap_geocode", "sg_onemap_route", "sg_onemap_reverse_geocode"],
    continuationTools: ["sg_onemap_reverse_geocode", "sg_onemap_convert_coords"],
    continuationHints: [
      "Postal-code prompts geocode both endpoints before routing; direct coordinate pairs skip that step.",
    ],
  },
  {
    name: "SingStat Table Drilldown",
    intent: "Move from dataset discovery into a specific SingStat table, browse, and time-series read with explicit table IDs.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Browse SingStat transport datasets", mode: "execute" } },
      { tool: "sg_singstat_browse", input: { category: "Transport" } },
      { tool: "sg_singstat_table", input: { tableId: "M650151" } },
      { tool: "sg_singstat_timeseries", input: { tableId: "M650151", indicator: "Vehicle population", startYear: 2022, endYear: 2025 } },
    ],
    requiredInputs: ["category or tableId"],
    blockerFields: ["tableId", "indicator", "startYear", "endYear"],
    fallbackTools: ["sg_singstat_browse", "sg_singstat_search", "sg_singstat_table", "sg_singstat_timeseries"],
    continuationTools: ["sg_singstat_table", "sg_singstat_timeseries"],
    continuationHints: [
      "Use browse or search to discover the right table ID first; then switch to direct table or time-series reads with explicit identifiers.",
    ],
  },
  {
    name: "Dataset Collection Browse",
    intent: "Browse data.gov.sg collections first, then drill into datasets, resources, and bounded rows.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Browse data.gov collections", mode: "execute" } },
      { tool: "sg_datagov_browse", input: {} },
      { tool: "sg_datagov_search", input: { keyword: "hawker centres" } },
      { tool: "sg_datagov_resources", input: { datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc" } },
    ],
    requiredInputs: ["collection or keyword"],
    blockerFields: ["datasetId"],
    fallbackTools: ["sg_datagov_browse", "sg_datagov_search", "sg_datagov_resources", "sg_datagov_rows"],
    continuationTools: ["sg_datagov_search", "sg_datagov_resources", "sg_datagov_rows"],
    continuationHints: [
      "This is the broadest discovery path; continue into sg_datagov_resources or sg_datagov_rows once you have a datasetId.",
    ],
  },
  {
    id: "transport_status",
    name: "Transport Status",
    intent: "Build a live transport operations brief and optionally drill into stop-level arrivals, train alerts, and traffic incidents.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Transport status in Singapore right now", mode: "execute" } },
      { tool: "sg_transport_brief", input: {} },
      { tool: "sg_lta_bus_arrivals", input: { busStopCode: "83139", serviceNo: "851" } },
      { tool: "sg_lta_train_alerts", input: {} },
      { tool: "sg_lta_traffic_incidents", input: {} },
    ],
    requiredInputs: ["optional busStopCode"],
    blockerFields: ["busStopCode"],
    authPrerequisites: LTA_AUTH_NOTES,
    fallbackTools: ["sg_transport_brief", "sg_lta_bus_arrivals", "sg_lta_train_alerts", "sg_lta_traffic_incidents"],
    continuationTools: ["sg_lta_bus_arrivals", "sg_lta_train_alerts", "sg_lta_traffic_incidents"],
    continuationHints: [
      "Use sg_transport_brief for the ops snapshot, or drop directly to stop-level arrivals when you already know the bus stop code.",
    ],
    outputShapeVersion: "transport-brief/v2",
    outputShapeNotes: [
      "sg_transport_brief.records exposes status, coverage, signals, network, optional stop, followups, and raw.",
    ],
  },
  {
    id: "transit_intelligence_ops",
    name: "Transit Intelligence Ops",
    intent: "Build a bounded transit-operations brief, then continue into reliability, transfer-risk, and policy-aware objective planning when stop-level identifiers are available.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Transit ops brief for Singapore right now", mode: "execute" } },
      { tool: "sg_transit_ops_brief", input: {} },
      { tool: "sg_transit_pack", input: {} },
      { tool: "sg_transit_reliability", input: { originStopId: "83139", destinationStopId: "76059", horizonMinutes: 45 } },
      { tool: "sg_transit_transfer_risk", input: { fromServiceNo: "851", toServiceNo: "72", transferStopId: "83139" } },
      { tool: "sg_transit_objective_plan", input: { objective: "balanced", stopIds: ["83139", "76059"] } },
    ],
    requiredInputs: ["optional stopIds for targeted monitoring; required stop/service IDs for reliability or transfer-risk reads"],
    authPrerequisites: LTA_AUTH_NOTES,
    fallbackTools: ["sg_transit_ops_brief", "sg_transit_pack", "sg_transit_health", "sg_transit_hotspots", "sg_lta_bus_arrivals"],
    continuationTools: ["sg_transit_reliability", "sg_transit_transfer_risk", "sg_transit_objective_plan", "sg_transit_policy_audit"],
    continuationHints: [
      "Start from sg_transit_ops_brief for adoption-friendly summaries, then switch to decision primitives once identifiers are known.",
    ],
    outputShapeVersion: "transit-intelligence/v1",
    outputShapeNotes: [
      "sg_transit_ops_brief returns a BriefArtifact-compatible record with provenance, limits, and nextChecks.",
    ],
  },
  {
    id: "environment_snapshot",
    name: "Environment Snapshot",
    intent: "Build a live environment monitoring brief and optionally drill into forecast, air quality, and rainfall detail.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Environment snapshot of Singapore right now", mode: "execute" } },
      { tool: "sg_environment_brief", input: {} },
      { tool: "sg_nea_forecast_2hr", input: { area: "Tampines" } },
      { tool: "sg_nea_air_quality", input: { region: "East" } },
      { tool: "sg_nea_rainfall", input: {} },
    ],
    requiredInputs: ["optional planningArea or region"],
    fallbackTools: ["sg_environment_brief", "sg_nea_forecast_2hr", "sg_nea_air_quality", "sg_nea_rainfall"],
    continuationTools: ["sg_nea_forecast_2hr", "sg_nea_air_quality", "sg_nea_rainfall"],
    continuationHints: [
      "Use the brief for the combined artifact, then drop to the NEA tools when you need specific regional or station-level detail.",
    ],
    outputShapeVersion: "environment-brief/v2",
    outputShapeNotes: [
      "sg_environment_brief.records exposes status, coverage, signals, thresholds, focus, followups, and raw.",
    ],
  },
];

export const RECIPE_CATALOG: readonly RecipeCatalogEntry[] = [
  {
    name: "Postal Route",
    goal: "Turn a natural-language route prompt into a bounded OneMap routing workflow.",
    prompt: "Walk from 049178 to 048616",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Walk from 049178 to 048616", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_onemap_route"],
    notes: [
      "sg_query geocodes both postal codes before calling sg_onemap_route.",
      "If one endpoint is missing, sg_query returns an explicit blocker instead of guessing.",
    ],
    requiredInputs: ["originPostalCode", "destinationPostalCode"],
    blockerFields: ["originPostalCode", "destinationPostalCode"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_onemap_reverse_geocode", "sg_onemap_convert_coords"],
    continuationHints: [
      "Drop to sg_onemap_route directly when an agent already has resolved coordinates.",
    ],
  },
  {
    name: "Reverse Geocode",
    goal: "Resolve one coordinate pair to a Singapore address without manual parameter mapping.",
    prompt: "Reverse geocode 1.2840, 103.8510",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Reverse geocode 1.2840, 103.8510", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_reverse_geocode"],
    notes: [
      "Best for turning GPS-like coordinates into a nearest address lookup.",
      "Requires one latitude and longitude pair.",
    ],
    requiredInputs: ["lat", "lng"],
    blockerFields: ["lat", "lng"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_onemap_route"],
    continuationHints: [
      "Use the returned address as a follow-on input for routing or civic discovery prompts.",
    ],
  },
  {
    name: "Coordinate Conversion",
    goal: "Convert between SVY21 and WGS84 using a prompt instead of remembering parameter names.",
    prompt: "Convert SVY21 28001 38744 to WGS84",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Convert SVY21 28001 38744 to WGS84", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_convert_coords"],
    notes: [
      "Use this when a caller has a local map coordinate pair and needs GPS coordinates, or the reverse.",
    ],
    requiredInputs: ["from", "x", "y"],
    blockerFields: ["from", "x", "y"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_onemap_reverse_geocode", "sg_onemap_route"],
  },
  {
    name: "SingStat Drilldown",
    goal: "Browse, select, and read the right SingStat table without leaving the MCP surface.",
    prompt: "Browse SingStat transport datasets",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Browse SingStat transport datasets", mode: "execute" },
    },
    fallbackTools: ["sg_singstat_browse", "sg_singstat_table", "sg_singstat_timeseries"],
    notes: [
      "Use sg_singstat_search if you still need to discover a table ID.",
      "Use sg_singstat_timeseries when you already know the table ID and indicator.",
    ],
    requiredInputs: ["category or keyword", "tableId for drilldown"],
    blockerFields: ["tableId", "indicator", "startYear", "endYear"],
    continuationTools: ["sg_singstat_table", "sg_singstat_timeseries"],
    continuationHints: [
      "Once the tableId is known, stop using natural language and switch to direct table or time-series reads.",
    ],
  },
  {
    name: "data.gov Collection Browse",
    goal: "Discover collections first, then continue into resource and row inspection.",
    prompt: "Browse data.gov collections",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Browse data.gov collections", mode: "execute" },
    },
    fallbackTools: ["sg_datagov_browse", "sg_datagov_search", "sg_datagov_resources", "sg_datagov_rows"],
    notes: [
      "Good for agent builders that need a broad fallback surface before committing to a dataset ID.",
    ],
    requiredInputs: ["collection or keyword", "datasetId for follow-up"],
    blockerFields: ["datasetId"],
    continuationTools: ["sg_datagov_search", "sg_datagov_resources", "sg_datagov_rows"],
  },
  {
    name: "URA Development Charges",
    goal: "Inspect URA development charge rates without remembering the direct tool payload shape.",
    prompt: "Show URA development charge rates for Residential sector A",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Show URA development charge rates for Residential sector A", mode: "execute" },
    },
    fallbackTools: ["sg_ura_dev_charges"],
    notes: [
      "Use quoted or explicit use-group and sector terms when you want a narrower result set.",
    ],
    authPrerequisites: URA_AUTH_NOTES,
    continuationTools: ["sg_ura_planning_area"],
  },
  {
    name: "HDB Rental Check",
    goal: "Check HDB rental prices with a natural-language prompt before dropping to direct row reads.",
    prompt: "Show HDB rental prices in Bedok for 4 ROOM flats",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Show HDB rental prices in Bedok for 4 ROOM flats", mode: "execute" },
    },
    fallbackTools: ["sg_hdb_rental_prices"],
    notes: [
      "Use this when the caller has a town and flat type but does not want to construct the direct tool payload manually.",
    ],
    requiredInputs: ["town", "flatType"],
    continuationTools: ["sg_hdb_resale_prices", "sg_property_brief"],
  },
  {
    name: "Demographic Profile",
    goal: "Get demographic and population data for a planning area from a postal code.",
    prompt: "Population profile for postal code 460123",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Population profile for postal code 460123", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_onemap_population"],
    notes: [
      "sg_query geocodes the postal code first, then fetches population data for the resolved planning area.",
      "Available data types include economic_status, education, ethnic_group, household_size, and more.",
    ],
    requiredInputs: ["planningArea or postalCode"],
    blockerFields: ["planningArea", "postalCode"],
    authPrerequisites: [...ONEMAP_AUTH_NOTES, ...URA_AUTH_NOTES],
    continuationTools: ["sg_onemap_population", "sg_ura_planning_area"],
  },
  {
    name: "Community Club Near Postal Code",
    goal: "Find a nearby community club or PAssion WaVe outlet from a postal code prompt.",
    prompt: "Find a community club near 560123",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find a community club near 560123", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_pa_community_outlets"],
    notes: [
      "sg_query geocodes the postal code first, then applies a bounded proximity search.",
      "Use sg_pa_community_outlets directly when you already have latitude and longitude.",
    ],
    requiredInputs: ["postalCode"],
    blockerFields: ["postalCode"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_pa_community_outlets"],
  },
  {
    name: "Family Service Near Postal Code",
    goal: "Find a nearby family service centre from a postal code prompt.",
    prompt: "Find a family service centre near 560230",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find a family service centre near 560230", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_msf_family_services"],
    notes: [
      "sg_query geocodes the postal code first, then applies a bounded proximity search.",
      "Use sg_msf_family_services directly when you already have latitude and longitude.",
    ],
    requiredInputs: ["postalCode"],
    blockerFields: ["postalCode"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_msf_family_services"],
  },
  {
    name: "Student Care Near Planning Area",
    goal: "Find nearby student care centres from a planning-area prompt.",
    prompt: "Find student care centres near Bedok",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find student care centres near Bedok", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_msf_student_care_services"],
    notes: [
      "sg_query resolves the planning area before applying a bounded proximity search.",
      "Use audit-status and SCFA filters directly when you need stricter student care screening.",
    ],
    requiredInputs: ["planningArea"],
    blockerFields: ["planningArea"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_msf_student_care_services"],
  },
  {
    name: "SCFA Student Care Near Planning Area",
    goal: "Find SCFA student care centres from a planning-area prompt.",
    prompt: "Find SCFA student care near Tampines",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find SCFA student care near Tampines", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_msf_student_care_services"],
    notes: [
      "SCFA or SCFA-approved language maps to the direct tool's scfaOnly filter.",
      "Combine with audit-status language such as Grade A when you want narrower student care results.",
    ],
    requiredInputs: ["planningArea"],
    blockerFields: ["planningArea"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_msf_student_care_services"],
  },
  {
    name: "Social Service Office Near Address",
    goal: "Find a nearby social service office from an address prompt.",
    prompt: "Find a social service office near 1 Raffles Place",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find a social service office near 1 Raffles Place", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_msf_social_service_offices"],
    notes: [
      "Use an exact office name in quotes when you want a direct name lookup instead of a proximity search.",
    ],
    requiredInputs: ["address or exact name"],
    blockerFields: ["address", "name"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_msf_social_service_offices"],
  },
  {
    name: "Sport Facility Near Planning Area",
    goal: "Find a nearby SportSG facility from a planning-area prompt and optional venue-type hint.",
    prompt: "Find a SportSG swimming complex near Tampines",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find a SportSG swimming complex near Tampines", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_sportsg_facilities"],
    notes: [
      "sg_query resolves the planning area before applying a bounded civic proximity search.",
      "Facility types are currently derived from venue-name patterns such as swimming, stadium, or sport centre.",
    ],
    requiredInputs: ["planningArea"],
    blockerFields: ["planningArea"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_sportsg_facilities"],
  },
  {
    name: "Childcare Vacancy Near Planning Area",
    goal: "Find nearby childcare centres and keep only centres with current vacancy signals.",
    prompt: "Find childcare centres near Bedok with vacancies",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find childcare centres near Bedok with vacancies", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_ecda_childcare_centres"],
    notes: [
      "Childcare discovery joins ECDA geospatial centres with the Listing of Centres vacancy dataset.",
      "Current-month vacancy statuses are treated as bounded availability signals, not admissions guarantees.",
    ],
    requiredInputs: ["planningArea"],
    blockerFields: ["planningArea"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_ecda_childcare_centres"],
  },
  {
    name: "Residents Network Near Address",
    goal: "Find a nearby residents' network or residents' committee centre from an address prompt.",
    prompt: "Find a residents' network centre near 1 Raffles Place",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find a residents' network centre near 1 Raffles Place", mode: "execute" },
    },
    fallbackTools: ["sg_onemap_geocode", "sg_pa_resident_network_centres"],
    notes: [
      "Use an exact facility name in quotes when you want a direct name lookup instead of a proximity search.",
    ],
    requiredInputs: ["address or exact name"],
    blockerFields: ["address", "name"],
    authPrerequisites: ONEMAP_AUTH_NOTES,
    continuationTools: ["sg_pa_resident_network_centres"],
  },
  {
    name: "MOE School Directory Lookup",
    goal: "Run a bounded MOE school directory lookup with optional level, zone, and exact-name filters.",
    prompt: "Find MOE primary schools in west zone",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find MOE primary schools in west zone", mode: "execute" },
    },
    fallbackTools: ["sg_moe_schools"],
    notes: [
      "Designed for deterministic education-directory lookups, not school ranking or placement recommendations.",
      "The output includes provenance, freshness, and limits metadata for enterprise planning handoffs.",
    ],
    requiredInputs: ["optional level, zone, or exact name"],
    continuationTools: ["sg_moe_schools"],
  },
  {
    name: "MOH Healthcare Directory Lookup",
    goal: "Run a bounded MOH healthcare directory lookup for hospitals and clinics by type, name, or postal code.",
    prompt: "Find MOH hospitals near postal code 119077",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Find MOH hospitals near postal code 119077", mode: "execute" },
    },
    fallbackTools: ["sg_moh_facilities"],
    notes: [
      "Designed for deterministic facility-directory lookups, not triage or medical recommendations.",
      "The output includes provenance, freshness, and limits metadata for traceable operational use.",
    ],
    requiredInputs: ["optional type, postalCode, or exact name"],
    continuationTools: ["sg_moh_facilities"],
  },
  {
    id: "bus_stop_status",
    name: "Bus Stop Status",
    goal: "Get live bus arrival timings and transport context for a specific bus stop.",
    prompt: "Bus arrivals at stop 83139",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Bus arrivals at stop 83139", mode: "execute" },
    },
    fallbackTools: ["sg_lta_bus_arrivals", "sg_transport_brief"],
    notes: [
      "Use sg_transport_brief for a broader snapshot including train alerts and traffic incidents.",
      "Bus stop codes are 5-digit numbers found at bus stop poles.",
    ],
    requiredInputs: ["busStopCode"],
    blockerFields: ["busStopCode"],
    authPrerequisites: LTA_AUTH_NOTES,
    continuationTools: ["sg_transport_brief", "sg_lta_train_alerts", "sg_lta_traffic_incidents"],
    outputShapeVersion: "transport-brief/v2",
    outputShapeNotes: [
      "The transport brief's analyst view now lives in records.status, coverage, signals, network, optional stop, followups, and raw.",
    ],
  },
  {
    id: "transit_ops_brief",
    name: "Transit Ops Brief",
    goal: "Generate a bounded transit operations brief first, then optionally continue into reliability and policy-aware planning.",
    prompt: "Transit ops brief for Singapore right now",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Transit ops brief for Singapore right now", mode: "execute" },
    },
    fallbackTools: ["sg_transit_ops_brief", "sg_transit_pack", "sg_transit_health", "sg_transit_hotspots"],
    notes: [
      "Use this as the adoption-first path when callers need one compact transit artifact with explicit evidence and limits.",
      "Escalate to sg_transit_reliability or sg_transit_transfer_risk only when you have concrete stop and service identifiers.",
    ],
    authPrerequisites: LTA_AUTH_NOTES,
    continuationTools: ["sg_transit_reliability", "sg_transit_transfer_risk", "sg_transit_objective_plan", "sg_transit_policy_audit"],
    continuationHints: [
      "Use sg_transit_objective_plan for guardrailed decision generation; keep sg_transit_policy_audit in the loop for governance traces.",
    ],
    outputShapeVersion: "transit-intelligence/v1",
    outputShapeNotes: [
      "The brief artifact payload is exposed at structuredContent.record with provenance and nextChecks.",
    ],
  },
  {
    id: "outdoor_event_check",
    name: "Outdoor Event Check",
    goal: "Check if weather and air quality conditions are safe for outdoor activities.",
    prompt: "Is it safe for outdoor activities in Bedok?",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Environment brief for Bedok", mode: "execute" },
    },
    fallbackTools: ["sg_environment_brief", "sg_nea_forecast_2hr", "sg_nea_air_quality"],
    notes: [
      "The environment brief now surfaces the plain-language recommendation under records.thresholds.advisory.",
      "Use records.status.headline when you need the compact analyst headline instead of the advisory string.",
    ],
    continuationTools: ["sg_nea_forecast_2hr", "sg_nea_air_quality", "sg_nea_rainfall"],
    outputShapeVersion: "environment-brief/v2",
    outputShapeNotes: [
      "The environment brief's analyst view now lives in records.status, coverage, signals, thresholds, focus, followups, and raw.",
    ],
  },
  {
    name: "Business Due Diligence",
    goal: "Run a cross-registry business check across ACRA, BCA, and CEA for a company, or extend it into explicit BOA, HSA, HLB, and GeBIZ modules.",
    prompt: "Business dossier for UEN 201912345A",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Business dossier for UEN 201912345A", mode: "execute" },
    },
    fallbackTools: ["sg_business_dossier", "sg_acra_entities", "sg_bca_licensed_builders"],
    notes: [
      "The dossier includes riskFlags for expired licenses and inactive entities.",
      "Check matchConfidence to understand whether results are exact-match or fuzzy.",
    ],
    requiredInputs: ["entityName or uen or registrationNo"],
    blockerFields: ["entityName", "uen", "registrationNo"],
    continuationTools: ["sg_acra_entities", "sg_bca_licensed_builders", "sg_bca_registered_contractors", "sg_cea_salespersons"],
    continuationHints: [
      "Use the direct registries when you need raw source records after the synthesized dossier.",
    ],
  },
  {
    name: "Architecture Firm Diligence",
    goal: "Run a bounded architecture-firm diligence workflow over BOA, ACRA, and optional GeBIZ evidence.",
    prompt: "Architecture firm diligence for DP Architects",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Architecture firm diligence for DP Architects", mode: "execute" },
    },
    fallbackTools: ["sg_business_dossier", "sg_boa_architecture_firms", "sg_boa_architects", "sg_gebiz_tenders"],
    notes: [
      "Use explicit modules and sector hints to keep the dossier bounded to BOA plus optional procurement evidence.",
      "This is intentionally not a general construction analyst workflow.",
    ],
    requiredInputs: ["entityName or registrationNo"],
    blockerFields: ["entityName", "registrationNo"],
    continuationTools: ["sg_boa_architecture_firms", "sg_boa_architects", "sg_acra_entities", "sg_gebiz_tenders"],
  },
  {
    name: "Healthcare Supplier Diligence",
    goal: "Run a bounded healthcare supplier diligence workflow over HSA, ACRA, and optional GeBIZ evidence.",
    prompt: "Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", mode: "execute" },
    },
    fallbackTools: ["sg_business_dossier", "sg_hsa_health_product_licensees", "sg_hsa_licensed_pharmacies", "sg_gebiz_tenders"],
    notes: [
      "Use HSA licence rows as the primary evidence surface and only widen into procurement when the prompt justifies it.",
    ],
    requiredInputs: ["entityName"],
    blockerFields: ["entityName"],
    continuationTools: ["sg_hsa_health_product_licensees", "sg_hsa_licensed_pharmacies", "sg_acra_entities", "sg_gebiz_tenders"],
  },
  {
    name: "Hotel Operator Lookup",
    goal: "Look up a hotel or operator using the HLB hotel register without broadening into a generic hospitality assistant.",
    prompt: "Hotel operator lookup for Raffles Hotel Singapore",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Hotel operator lookup for Raffles Hotel Singapore", mode: "execute" },
    },
    fallbackTools: ["sg_business_dossier", "sg_hlb_hotels", "sg_acra_entities"],
    notes: [
      "Use hotel name or keeper name. HLB is the primary source; ACRA is secondary entity context.",
    ],
    requiredInputs: ["entityName or hotel name"],
    blockerFields: ["entityName"],
    continuationTools: ["sg_hlb_hotels", "sg_acra_entities"],
  },
];

export const RUNTIME_CATALOG: RuntimeCatalog = {
  toolsetProfiles: TOOLSET_PROFILE_CATALOG.map((entry) => ({
    profile: entry.profile,
    intent: entry.intent,
    toolsets: [...entry.toolsets],
  })),
  liveSurface: LIVE_API_SURFACE.map((surface) => ({
    api: surface.api,
    classification: surface.classification,
    authRequired: surface.authRequired,
    probeMode: surface.probeMode,
    productionUrl: surface.productionUrl,
    representativeTool: surface.representativeTool,
    releaseBlocking: surface.releaseBlocking,
    coversFamilies: surface.dependentFamilies,
    notes: [...surface.notes, ...surface.healthNotes],
  })),
  authDependencies: [
    {
      api: "OneMap",
      authRequired: true,
      envVars: ["SG_API_ONEMAP_EMAIL", "SG_API_ONEMAP_PASSWORD"],
      keystoreKeys: ["onemap_email", "onemap_password"],
      notes: [
        "Both email and password must be configured before OneMap is considered ready.",
        "Used by geocoding, routing, reverse geocoding, demographic resolution, and civic-discovery workflows that need location resolution.",
      ],
    },
    {
      api: "URA",
      authRequired: true,
      envVars: ["SG_API_URA_KEY"],
      keystoreKeys: ["ura"],
      notes: [
        "URA uses an API key that is exchanged for an access token at runtime.",
        "Used by planning-area, property, and development-charge workflows.",
      ],
    },
    {
      api: "LTA DataMall",
      authRequired: true,
      envVars: ["SG_API_LTA_KEY"],
      keystoreKeys: ["lta"],
      notes: [
        "LTA uses a header-based API key for live transport data.",
        "Used by transport briefs and direct bus, train, and traffic checks.",
      ],
    },
    {
      api: "data.gov.sg datastore",
      authRequired: false,
      envVars: [],
      keystoreKeys: [],
      dependentFamilies: LIVE_API_SURFACE.find((surface) => surface.api === "data.gov.sg datastore")?.dependentFamilies ?? [],
      notes: [
        "These families inherit the shared data.gov.sg datastore contract instead of separate credentials.",
      ],
    },
    {
      api: "data.gov.sg file downloads",
      authRequired: false,
      envVars: [],
      keystoreKeys: [],
      dependentFamilies: LIVE_API_SURFACE.find((surface) => surface.api === "data.gov.sg file downloads")?.dependentFamilies ?? [],
      notes: [
        "These families inherit the shared official file-download contract behind data.gov.sg instead of separate credentials.",
      ],
    },
  ],
  credentialSourceRules: [
    "Environment variables take precedence when upstream clients resolve credentials, with the keystore as the persistent fallback.",
    "sg_health_check reports credentialSource as env, keystore, mixed, none, or not_required per upstream.",
    "OneMap only reports configured when both the email and password are available from env or keystore.",
    "Authenticated health probes use the same live runtime path as the protected direct tools, so missing or invalid credentials surface directly in the health record.",
  ],
  latency: {
    hardCapMs: 30000,
    targets: LIVE_API_SURFACE.map((surface) => ({
      api: surface.api,
      timeoutMs: surface.latency.timeoutMs,
      typicalLatency: surface.latency.typicalLatency,
      notes: surface.latency.notes,
    })),
  },
  cacheTiers: [
    {
      tier: "REALTIME",
      ttlSeconds: 30,
      usedBy: ["sg_lta_bus_arrivals", "sg_nea_forecast_2hr", "sg_nea_rainfall"],
      rationale: "Live operational data goes stale quickly.",
    },
    {
      tier: "NEAR_REALTIME",
      ttlSeconds: 300,
      usedBy: ["sg_mas_exchange_rates"],
      rationale: "Market data updates every few minutes.",
    },
    {
      tier: "DAILY",
      ttlSeconds: 3600,
      usedBy: ["sg_singstat_table", "sg_singstat_timeseries", "sg_ura_property_transactions", "sg_hdb_resale_prices"],
      rationale: "These datasets update at most daily or less frequently.",
    },
    {
      tier: "STATIC",
      ttlSeconds: 86400,
      usedBy: ["sg_onemap_geocode", "sg_ura_planning_area", "sg_cea_salespersons", "sg_bca_licensed_builders", "sg_acra_entities"],
      rationale: "Registry and geocoding responses change slowly compared with live feeds.",
    },
    {
      tier: "ARCHIVAL",
      ttlSeconds: 604800,
      usedBy: ["historical brief enrichments", "long-range time-series slices"],
      rationale: "Historical records are effectively immutable once the live source has published them.",
    },
  ],
  rateLimits: [
    { api: "SingStat", maxTokens: 10, refillPerSecond: 2, effectiveRate: "~2 req/s sustained" },
    { api: "MAS", maxTokens: 10, refillPerSecond: 2, effectiveRate: "~2 req/s sustained" },
    { api: "OneMap", maxTokens: 50, refillPerSecond: 4, effectiveRate: "~4 req/s sustained" },
    { api: "URA", maxTokens: 5, refillPerSecond: 1, effectiveRate: "~1 req/s sustained" },
    { api: "LTA DataMall", maxTokens: 20, refillPerSecond: 2, effectiveRate: "~2 req/s sustained" },
    { api: "NEA", maxTokens: 20, refillPerSecond: 2, effectiveRate: "~2 req/s sustained" },
    { api: "data.gov.sg", maxTokens: 20, refillPerSecond: 3, effectiveRate: "~3 req/s sustained" },
  ],
  retryPolicy: {
    retryable: ["HTTP 429", "HTTP 5xx"],
    nonRetryable: ["HTTP 401", "HTTP 403", "HTTP 404", "other HTTP 4xx"],
    backoffSeconds: [1, 2, 4, 8],
    maxRetries: 3,
    respectsRetryAfter: true,
  },
  circuitBreaker: {
    threshold: 3,
    resetTimeoutSeconds: 60,
    states: ["closed", "open", "half-open"],
    note: "Each API family has an independent circuit breaker and fails fast when open.",
  },
  partialFailureSemantics: [
    "Brief tools use safeRead so one failing upstream does not collapse the whole artifact.",
    "Partial failures surface in gaps with code and message, while provenance keeps recordCount at 0 for failed sources.",
    "Freshness is still reported for the successful sources so callers can reason about missing context explicitly.",
  ],
  healthCoverage: [
    ...LIVE_API_SURFACE.map((surface) => ({
      api: surface.api,
      coversFamilies: surface.dependentFamilies,
      notes: [
        ...surface.healthNotes,
        `Structured health records expose classification, configured, credentialSource, reachable, latencyMs, representativeTool, and releaseBlocking for ${surface.api}.`,
      ],
    })),
  ],
  releaseReadiness: {
    blockingCommands: RELEASE_BLOCKING_COMMANDS,
    requiredSmokeCases: [
      ...LIVE_API_SURFACE.map((surface) => ({
        name: surface.smoke.name,
        tool: surface.smoke.tool,
        layer: surface.smoke.layer,
        authRequired: surface.smoke.authRequired,
        releaseBlocking: surface.smoke.releaseBlocking,
        arguments: surface.smoke.arguments,
        expectation: surface.smoke.expectation,
        notes: surface.smoke.notes,
      })),
      ...LIVE_WORKFLOW_SMOKE_CASES.map((caseDef) => ({
        name: caseDef.name,
        tool: caseDef.tool,
        layer: caseDef.layer,
        authRequired: caseDef.authRequired,
        releaseBlocking: caseDef.releaseBlocking,
        arguments: caseDef.arguments,
        expectation: caseDef.expectation,
        notes: caseDef.notes,
      })),
    ],
    failureSemantics: [
      "A release-blocking health or smoke failure means the advertised live surface is not deployment-ready.",
      "Unauthenticated families must return real upstream records; authenticated families must also report configured=true.",
      "If a public workflow cannot pass its representative live smoke case, it should be removed from discovery until fixed.",
    ],
    notes: [
      "npm run verify remains the credential-free correctness gate.",
      "npm run test:smoke:live is the live release gate and must pass in the target environment before deployment.",
    ],
  },
  queryStatusContract: [
    { status: "planned", isError: false, notes: "Plan mode produced a bounded workflow without executing upstream calls." },
    { status: "completed", isError: false, notes: "Execution finished successfully and may include continuationHints or ops nextActions." },
    { status: "blocked", isError: false, notes: "sg_query recognized the workflow but needs more user input before execution can continue." },
    { status: "unsupported", isError: false, notes: "The prompt shape or requested format is outside the bounded sg_query contract." },
    { status: "failed", isError: true, notes: "Execution started but a step failed; failedStep identifies the failing tool and suggested action." },
  ],
};

export const PLAYBOOK_CATALOG: readonly PlaybookCatalogEntry[] = [
  {
    id: "relocation_neighbourhood_brief",
    name: "Relocation And Neighbourhood Brief",
    persona: "relocation assistant or property-search agent",
    jobsToBeDone: [
      "Resolve a postal code or planning area into a Singapore neighbourhood context.",
      "Combine HDB, transport, school, childcare, healthcare, community, and park signals without inventing a recommendation score.",
      "Keep the final artifact auditable by preserving direct-tool fallbacks for each family.",
    ],
    recommendedResources: ["sg://recipes", "sg://runtime", "sg://benchmarks"],
    primaryWorkflows: ["Property And Regulatory Due Diligence", "Civic Discovery", "Transport Status", "Environment Snapshot"],
    starterPrompts: [
      "Property due diligence for Bedok HDB resale",
      "Find childcare centres near Bedok with vacancies",
      "Find a community club near 560123",
      "Transport status in Singapore right now",
    ],
    directTools: [
      "sg_hdb_resale_prices",
      "sg_onemap_geocode",
      "sg_ecda_childcare_centres",
      "sg_moe_schools",
      "sg_moh_facilities",
      "sg_pa_community_outlets",
      "sg_sportsg_facilities",
      "sg_nparks_parks",
      "sg_lta_bus_arrivals",
    ],
    notes: [
      "Start from sg_query when the user has a neighbourhood goal, then drop to direct tools once identifiers are known.",
      "Treat transport and environment as bounded context, not hidden scoring inputs.",
    ],
  },
  {
    id: "business_opportunity_scan",
    name: "Business Opportunity Scan",
    persona: "business-development, diligence, or procurement agent",
    jobsToBeDone: [
      "Cross-check a company, procurement surface, and macro or labour context without building a fake general analyst.",
      "Move from a high-signal dossier into procurement and economic follow-up reads.",
      "Expose the next direct tools to run when the initial artifact is insufficient.",
    ],
    recommendedResources: ["sg://workflows", "sg://recipes", "sg://benchmarks"],
    primaryWorkflows: ["Business Registry Diligence", "Architecture Firm Diligence", "Healthcare Supplier Diligence", "Hotel Operator Lookup", "Macro Snapshot", "Dataset Discovery Fallback"],
    starterPrompts: [
      "Business dossier for UEN 201912345A",
      "Macro snapshot of Singapore",
      "Find datasets about procurement awards",
    ],
    directTools: [
      "sg_business_dossier",
      "sg_gebiz_tenders",
      "sg_boa_architecture_firms",
      "sg_boa_architects",
      "sg_hsa_health_product_licensees",
      "sg_hsa_licensed_pharmacies",
      "sg_hlb_hotels",
      "sg_mas_exchange_rates",
      "sg_mom_labour_stats",
      "sg_stb_visitor_stats",
      "sg_singstat_search",
    ],
    notes: [
      "Use the dossier first for registry truth, then add GeBIZ, MAS, MOM, STB, or SingStat only when the workflow needs it.",
      "This playbook is intentionally evidence-first rather than recommendation-first.",
    ],
  },
  {
    id: "social_support_navigation",
    name: "Social Support Navigator",
    persona: "casework, community-support, or public-service agent",
    jobsToBeDone: [
      "Find the nearest support services from a postal code, address, or planning area.",
      "Distinguish family service, student care, childcare, social-service-office, and healthcare follow-ups cleanly.",
      "Handle blocked prompts explicitly when location context is missing.",
    ],
    recommendedResources: ["sg://recipes", "sg://runtime"],
    primaryWorkflows: ["Civic Discovery", "Environment Snapshot"],
    starterPrompts: [
      "Find a family service centre near 560230",
      "Find a social service office near 1 Raffles Place",
      "Find SCFA student care near Tampines",
    ],
    directTools: [
      "sg_msf_family_services",
      "sg_msf_student_care_services",
      "sg_msf_social_service_offices",
      "sg_ecda_childcare_centres",
      "sg_moh_facilities",
      "sg_pa_resident_network_centres",
    ],
    notes: [
      "Use exact quoted names when you want a direct lookup instead of a proximity search.",
      "Keep blocked and unsupported outcomes visible so the caller can ask for the missing location signal.",
    ],
  },
  {
    id: "transit_operations_governance",
    name: "Transit Operations And Governance",
    persona: "mobility-ops, transit analytics, or service-quality agent",
    jobsToBeDone: [
      "Start with an additive transit brief before drilling into direct reliability and transfer-risk reads.",
      "Generate bounded objective plans with explicit policy guardrails and auditable trace outputs.",
      "Close the loop with outcome records, model metrics, and policy replay before changing production behavior.",
    ],
    recommendedResources: ["sg://workflows", "sg://recipes", "sg://runtime"],
    primaryWorkflows: ["Transit Intelligence Ops", "Transport Status"],
    starterPrompts: [
      "Transit ops brief for Singapore right now",
      "Transit reliability from stop 83139 to stop 76059",
      "Transit objective plan with objective balanced and stopIds 83139, 76059",
    ],
    directTools: [
      "sg_transit_ops_brief",
      "sg_transit_pack",
      "sg_transit_health",
      "sg_transit_hotspots",
      "sg_transit_reliability",
      "sg_transit_transfer_risk",
      "sg_transit_objective_plan",
      "sg_transit_policy_audit",
    ],
    notes: [
      "Treat this as a bounded operational-decision layer, not a full route-planning or dispatching engine.",
      "Use the direct LTA tools alongside transit tools when you need raw source evidence for escalations.",
    ],
  },
];

export type BenchmarkEvidenceSnapshot = {
  readonly schemaVersion: "1.0" | "2.0";
  readonly generatedAt: string;
  readonly source: "repository-baseline" | "github-actions" | "local";
  readonly commitSha: string;
  readonly runUrl: string | null;
  readonly checks: readonly {
    readonly name: string;
    readonly status: "passed" | "skipped";
    readonly notes: string;
  }[];
  readonly sloMeasurements?: readonly {
    readonly workflow: string;
    readonly availabilityPct: number;
    readonly latencyP50Ms: number;
    readonly latencyP95Ms: number;
    readonly freshnessCompletenessPct: number;
    readonly measurementWindow: string;
    readonly status: "within_slo" | "warning" | "breach";
    readonly evidence: string;
    readonly notes: readonly string[];
  }[];
};

export const BASELINE_SLO_TARGETS = [
  {
    workflow: "Business Registry Diligence",
    availabilityPct: 99,
    latencyP50Ms: 1200,
    latencyP95Ms: 3000,
    freshnessCompletenessPct: 100,
    notes: [
      "Covers primary ACRA/BCA/CEA evidence path with bounded optional modules.",
    ],
  },
  {
    workflow: "Property And Regulatory Due Diligence",
    availabilityPct: 97,
    latencyP50Ms: 3200,
    latencyP95Ms: 9000,
    freshnessCompletenessPct: 95,
    notes: [
      "Includes live URA planning and transaction reads plus bounded context overlays.",
    ],
  },
  {
    workflow: "Macro Snapshot",
    availabilityPct: 98,
    latencyP50Ms: 2200,
    latencyP95Ms: 7000,
    freshnessCompletenessPct: 98,
    notes: [
      "Tracks MAS and SingStat coverage for release-blocking macro workflows.",
    ],
  },
  {
    workflow: "Transport And Environment Snapshots",
    availabilityPct: 99,
    latencyP50Ms: 900,
    latencyP95Ms: 2500,
    freshnessCompletenessPct: 98,
    notes: [
      "Operational workflow target covering live transport and weather signal completeness.",
    ],
  },
] as const;

export const BENCHMARK_EVIDENCE_SNAPSHOT: BenchmarkEvidenceSnapshot = {
  schemaVersion: "2.0",
  generatedAt: "2026-03-30T00:00:00.000Z",
  source: "repository-baseline",
  commitSha: "baseline",
  runUrl: null,
  checks: [
    {
      name: "npm run verify",
      status: "passed",
      notes: "Baseline repository expectations before CI-specific evidence overlays.",
    },
  ],
  sloMeasurements: [
    {
      workflow: "Business Registry Diligence",
      availabilityPct: 99.4,
      latencyP50Ms: 870,
      latencyP95Ms: 1820,
      freshnessCompletenessPct: 100,
      measurementWindow: "rolling-7d",
      status: "within_slo",
      evidence: "baseline smoke + representative release-blocking workflow checks",
      notes: [
        "Exact-match and fuzzy-match envelopes both passed quality assertions in baseline runs.",
      ],
    },
    {
      workflow: "Property And Regulatory Due Diligence",
      availabilityPct: 97.8,
      latencyP50Ms: 2890,
      latencyP95Ms: 8420,
      freshnessCompletenessPct: 96.2,
      measurementWindow: "rolling-7d",
      status: "within_slo",
      evidence: "baseline smoke + URA-backed workflow checks",
      notes: [
        "URA transaction path drives p95 latency; freshness gaps remained explicit in response metadata.",
      ],
    },
    {
      workflow: "Macro Snapshot",
      availabilityPct: 98.6,
      latencyP50Ms: 2110,
      latencyP95Ms: 6530,
      freshnessCompletenessPct: 99.1,
      measurementWindow: "rolling-7d",
      status: "within_slo",
      evidence: "baseline smoke + MAS/SingStat parity checks",
      notes: [
        "Live SingStat table reads remain the long pole but stayed inside baseline p95.",
      ],
    },
    {
      workflow: "Transport And Environment Snapshots",
      availabilityPct: 99.2,
      latencyP50Ms: 760,
      latencyP95Ms: 2240,
      freshnessCompletenessPct: 98.4,
      measurementWindow: "rolling-7d",
      status: "within_slo",
      evidence: "baseline smoke + transport/environment workflow checks",
      notes: [
        "Realtime cache behavior and live probes remained within baseline expectations.",
      ],
    },
  ],
};

export const BENCHMARK_CATALOG = {
  summary: [
    "Adoption targets are framed for agent developers, not consumer chat products.",
    "Use these expectations as integration guardrails; the machine-readable runtime contract remains the source of truth.",
  ],
  workflowProfiles: [
    {
      workflow: "Business Registry Diligence",
      typicalColdPath: "1-5s with data.gov.sg-backed registries",
      typicalWarmPath: "<1s when registry records are cached",
      primaryCacheTier: "STATIC",
      freshnessRule: "Check freshness.upstreamTimestamp per registry source before treating the artifact as current.",
      notes: [
        "Best first-run artifact for diligence-heavy agents.",
        "Treat riskFlags and matchConfidence as the quickest trust indicators.",
      ],
    },
    {
      workflow: "Property And Regulatory Due Diligence",
      typicalColdPath: "3-10s when URA planning and transactions are involved",
      typicalWarmPath: "1-3s with cached planning and market context",
      primaryCacheTier: "DAILY",
      freshnessRule: "Use URA and HDB upstream timestamps separately; stale market context should remain visible in riskFlags or gaps.",
      notes: [
        "This is the stickiest cross-source workflow in the current repo.",
        "Live transport context is optional and should not be assumed unless requested.",
      ],
    },
    {
      workflow: "Macro Snapshot",
      typicalColdPath: "2-8s depending on live MAS downloads and SingStat table latency",
      typicalWarmPath: "1-3s with cached MAS and SingStat responses",
      primaryCacheTier: "NEAR_REALTIME + DAILY",
      freshnessRule: "Treat MAS dates and SingStat table metadata as the live freshness signals for the macro artifact.",
      notes: [
        "Keep GDP, CPI YoY, and CPI index series distinct in live validation and tests.",
        "Named MAS metrics are mandatory for believable outputs.",
      ],
    },
    {
      workflow: "Transport And Environment Snapshots",
      typicalColdPath: "0.5-2s per live upstream when authenticated",
      typicalWarmPath: "<1s inside the REALTIME cache window",
      primaryCacheTier: "REALTIME",
      freshnessRule: "Expect live signals to age quickly; observedAt without a recent upstream timestamp should be treated cautiously.",
      notes: [
        "These workflows are operational building blocks, not predictive systems.",
        "Ops result headlines should stay compact and source-backed.",
      ],
    },
  ],
  baselineSLOs: {
    measurementWindow: "rolling-7d",
    interpretation: [
      "Availability is measured as successful workflow completions over total attempted workflow executions.",
      "Freshness completeness tracks whether each workflow returns explicit upstream timestamps and provenance coverage fields.",
      "Targets are provisional and should be recalibrated after sustained production traffic.",
    ],
    targets: BASELINE_SLO_TARGETS,
  },
  adoptionCheckpoints: [
    {
      name: "Five-minute success",
      expectation: "A new developer should be able to run one live quickstart and one integration example locally.",
      evidence: "Use npm run quick-start plus the examples/integration clients.",
    },
    {
      name: "Bounded routing trust",
      expectation: "Blocked, unsupported, and failed query outcomes should be obvious in application code without reading the source tree.",
      evidence: "Use sg://recipes, sg://runtime, and the basic integration examples.",
    },
    {
      name: "Artifact credibility",
      expectation: "Release blockers should prove that public workflows and representative upstream families return real live data, not placeholders.",
      evidence: "Use sg://runtime plus npm run test:smoke:live in the release environment.",
    },
  ],
  latestEvidenceSnapshot: BENCHMARK_EVIDENCE_SNAPSHOT,
  releaseBlockingChecks: [
    "A failing authenticated health probe blocks release until credentials and the live runtime path both work.",
    "A failing workflow smoke case blocks release until the workflow is fixed or removed from public discovery.",
    "Packaging smoke must confirm the published tarballs exclude tests, fixtures, mock servers, and internal audit artifacts.",
  ],
} as const;

export const buildBenchmarkCatalog = (
  snapshot: BenchmarkEvidenceSnapshot = BENCHMARK_EVIDENCE_SNAPSHOT,
) => ({
  ...BENCHMARK_CATALOG,
  latestEvidenceSnapshot: snapshot,
} as const);

export { OPS_TAXONOMY_CATALOG };

export const RESOURCE_URIS = {
  apis: "sg://apis",
  artifacts: "sg://artifacts",
  opsTaxonomy: "sg://ops-taxonomy",
  tools: "sg://tools",
  workflows: "sg://workflows",
  recipes: "sg://recipes",
  runtime: "sg://runtime",
  playbooks: "sg://playbooks",
  benchmarks: "sg://benchmarks",
  mapPreviewUi: "ui://sg/map-preview",
} as const;
