import type { ToolCatalogEntry } from "./tool-definition.js";
import { toToolCatalogEntry } from "./tool-definition.js";
import { ALL_TOOL_DEFINITIONS } from "./tool-set.js";

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
  readonly name: string;
  readonly intent: string;
  readonly entrypoints: readonly {
    readonly tool: string;
    readonly input: Readonly<Record<string, unknown>>;
  }[];
};

export type RecipeCatalogEntry = {
  readonly name: string;
  readonly goal: string;
  readonly prompt: string;
  readonly preferredEntrypoint: {
    readonly tool: string;
    readonly input: Readonly<Record<string, unknown>>;
  };
  readonly fallbackTools: readonly string[];
  readonly notes: readonly string[];
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
    tools: ["sg_lta_bus_arrivals", "sg_lta_train_alerts", "sg_lta_traffic_incidents"],
    authRequired: true,
    rateLimit: "20 tokens, 2/sec refill",
    positioning: "Primary transport-status surface for live operational checks.",
    preferredInterface: "sg_query",
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

export const WORKFLOW_CATALOG: readonly WorkflowCatalogEntry[] = [
  {
    name: "Macro Snapshot",
    intent: "Build a compact Singapore macro starter brief with MAS values and SingStat entrypoints.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Macro snapshot of Singapore", mode: "execute" } },
      { tool: "sg_macro_brief", input: { currency: "USD" } },
      { tool: "sg_mas_exchange_rates", input: { currency: "USD", startDate: "2026-03-01", endDate: "2026-03-26" } },
      { tool: "sg_singstat_search", input: { keyword: "Singapore GDP" } },
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
  },
  {
    name: "Business Registry Diligence",
    intent: "Build a cross-registry business dossier across ACRA, BCA, and CEA records.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Registry diligence for UEN 201912345K", mode: "execute" } },
      { tool: "sg_business_dossier", input: { uen: "201912345K" } },
      { tool: "sg_acra_entities", input: { uen: "201912345K" } },
      { tool: "sg_bca_licensed_builders", input: { companyName: "ABC CONSTRUCTION PTE LTD" } },
      { tool: "sg_bca_registered_contractors", input: { companyName: "ABC CONSTRUCTION PTE LTD" } },
      { tool: "sg_cea_salespersons", input: { registrationNo: "R123456A" } },
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
  },
  {
    name: "Route Planning",
    intent: "Plan directions between two Singapore postal codes or coordinate pairs using OneMap geocoding and routing.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Walk from 049178 to 048616", mode: "execute" } },
      { tool: "sg_onemap_route", input: { startLat: 1.2864, startLng: 103.8537, endLat: 1.284, endLng: 103.851, routeType: "walk" } },
      { tool: "sg_onemap_reverse_geocode", input: { lat: 1.284, lng: 103.851 } },
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
  },
  {
    name: "Transport Status",
    intent: "Build a live transport operations brief and optionally drill into stop-level arrivals, train alerts, and traffic incidents.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Transport status in Singapore right now", mode: "execute" } },
      { tool: "sg_transport_brief", input: {} },
      { tool: "sg_lta_bus_arrivals", input: { busStopCode: "83139", serviceNo: "851" } },
      { tool: "sg_lta_train_alerts", input: {} },
      { tool: "sg_lta_traffic_incidents", input: {} },
    ],
  },
  {
    name: "Environment Snapshot",
    intent: "Build a live environment monitoring brief and optionally drill into forecast, air quality, and rainfall detail.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Environment snapshot of Singapore right now", mode: "execute" } },
      { tool: "sg_environment_brief", input: {} },
      { tool: "sg_nea_forecast_2hr", input: { area: "Tampines" } },
      { tool: "sg_nea_air_quality", input: { region: "East" } },
      { tool: "sg_nea_rainfall", input: {} },
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
  },
  {
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
  },
  {
    name: "Outdoor Event Check",
    goal: "Check if weather and air quality conditions are safe for outdoor activities.",
    prompt: "Is it safe for outdoor activities in Bedok?",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Environment brief for Bedok", mode: "execute" },
    },
    fallbackTools: ["sg_environment_brief", "sg_nea_forecast_2hr", "sg_nea_air_quality"],
    notes: [
      "The environment brief includes an outdoorConditions advisory derived from forecast, air quality, and rainfall.",
      "Check the outdoorConditions.advisory field for a plain-language recommendation.",
    ],
  },
  {
    name: "Business Due Diligence",
    goal: "Run a cross-registry business check across ACRA, BCA, and CEA for a company.",
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
  },
];

export const RESOURCE_URIS = {
  apis: "sg://apis",
  tools: "sg://tools",
  workflows: "sg://workflows",
  recipes: "sg://recipes",
} as const;
