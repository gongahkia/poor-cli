export type LiveSurfaceClassification =
  | "live_public"
  | "live_authenticated"
  | "shared_datagov_datastore"
  | "shared_file_download";

export type SmokeExpectation =
  | Readonly<{ kind: "records_non_empty"; key?: "records" }>
  | Readonly<{ kind: "brief_artifact"; title: string; minimumProvenanceCount?: number }>
  | Readonly<{ kind: "query_completed"; workflow: string }>;

export type SmokeCase = Readonly<{
  id: string;
  name: string;
  layer: "api" | "workflow";
  authRequired: boolean;
  releaseBlocking: boolean;
  tool: string;
  arguments: Readonly<Record<string, unknown>>;
  expectation: SmokeExpectation;
  notes: readonly string[];
}>;

export type LiveSurfaceDefinition = Readonly<{
  api: string;
  classification: LiveSurfaceClassification;
  authRequired: boolean;
  envVars: readonly string[];
  keystoreKeys: readonly string[];
  productionUrl: string;
  probeMode: "runtime_client";
  releaseBlocking: boolean;
  representativeTool: string;
  dependentFamilies: readonly string[];
  notes: readonly string[];
  healthNotes: readonly string[];
  latency: Readonly<{
    timeoutMs: number;
    typicalLatency: string;
    notes: string;
  }>;
  smoke: SmokeCase;
}>;

export const DATAGOV_DATASTORE_FAMILIES = [
  "HDB",
  "CEA",
  "BCA",
  "ACRA",
  "GeBIZ",
  "Hawker Centres",
  "MOE Schools",
  "MOH Healthcare",
  "SFA",
  "NParks",
  "PUB",
  "MOM",
  "STB",
] as const;

export const DATAGOV_FILE_DOWNLOAD_FAMILIES = [
  "BOA",
  "PA",
  "Sport Singapore",
  "ECDA",
  "MSF Family Services",
  "MSF Student Care Services",
  "MSF Social Service Offices",
  "HSA",
  "HLB",
] as const;

export const GOV_FEED_FAMILIES = [
  "Government RSS Feeds",
] as const;

export const LIVE_API_SURFACE: readonly LiveSurfaceDefinition[] = [
  {
    api: "SingStat",
    classification: "live_public",
    authRequired: false,
    envVars: [],
    keystoreKeys: [],
    productionUrl: "https://tablebuilder.singstat.gov.sg/api/table",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_singstat_table",
    dependentFamilies: ["SingStat"],
    notes: [
      "Public SingStat access is live-only and uses the official Table Builder API.",
      "Macro workflows depend on validated table reads rather than dataset-search placeholders.",
    ],
    healthNotes: [
      "Probed through the live SingStat client against a validated table ID.",
      "Release readiness fails if the runtime table-read path cannot return real rows.",
    ],
    latency: {
      timeoutMs: 15000,
      typicalLatency: "2-8s",
      notes: "Large table reads can be slow even for bounded live requests.",
    },
    smoke: {
      id: "api-singstat",
      name: "SingStat table read",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_singstat_table",
      arguments: {
        tableId: "M015631",
        variables: ["GDP At Current Market Prices"],
        format: "json",
      },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises the same live table-read contract used by the macro brief."],
    },
  },
  {
    api: "MAS",
    classification: "live_public",
    authRequired: false,
    envVars: [],
    keystoreKeys: [],
    productionUrl: "https://eservices.mas.gov.sg/statistics",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_mas_exchange_rates",
    dependentFamilies: ["MAS"],
    notes: [
      "MAS access uses live statistics pages and CSV downloads, not the old CKAN datastore contract.",
      "Exchange rates, SORA, and banking statistics share the same live runtime model.",
    ],
    healthNotes: [
      "Probed through the live MAS CSV download flow.",
      "Release readiness fails if the runtime downloader cannot fetch or parse the current MAS contract.",
    ],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "1-3s",
      notes: "MAS CSV downloads are moderately sized but usually responsive.",
    },
    smoke: {
      id: "api-mas",
      name: "MAS exchange rates",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_mas_exchange_rates",
      arguments: {
        currency: "USD",
        format: "json",
      },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises the live MAS download and normalization path."],
    },
  },
  {
    api: "OneMap",
    classification: "live_authenticated",
    authRequired: true,
    envVars: ["SG_API_ONEMAP_EMAIL", "SG_API_ONEMAP_PASSWORD"],
    keystoreKeys: ["onemap_email", "onemap_password"],
    productionUrl: "https://www.onemap.gov.sg/api",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_onemap_geocode",
    dependentFamilies: ["OneMap"],
    notes: [
      "Both the email and password must be configured before OneMap is considered live-ready.",
      "Civic and geospatial workflows rely on the same authenticated geocoding path.",
      "Paid hosted use must read sg://runtime sourceUseWarnings because OneMap-backed redistribution remains blocked until Developer Agreement rights are reviewed.",
    ],
    healthNotes: [
      "Probed through the same authenticated runtime client used by live direct tools and workflow geocoding.",
      "Missing or invalid credentials surface as health failures rather than hidden fallbacks.",
    ],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "0.5-2s",
      notes: "Token refresh can add about one second to the first call.",
    },
    smoke: {
      id: "api-onemap",
      name: "OneMap geocode",
      layer: "api",
      authRequired: true,
      releaseBlocking: true,
      tool: "sg_onemap_geocode",
      arguments: {
        searchVal: "049178",
        limit: 1,
        format: "json",
      },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises live geocoding with a known Singapore postal code."],
    },
  },
  {
    api: "URA",
    classification: "live_authenticated",
    authRequired: true,
    envVars: ["SG_API_URA_KEY"],
    keystoreKeys: ["ura"],
    productionUrl: "https://www.ura.gov.sg/uraDataService",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_ura_dev_charges",
    dependentFamilies: ["URA"],
    notes: [
      "URA uses an API key that is exchanged for an access token at runtime.",
      "Planning-area and property workflows rely on the same authenticated runtime path.",
      "Commercial URA-backed workflows must preserve Singapore Open Data Licence attribution and any API-page-specific limits.",
    ],
    healthNotes: [
      "Probed through the live URA runtime client rather than a bare token endpoint fetch.",
      "Release readiness fails if token exchange or the real data path is unhealthy.",
    ],
    latency: {
      timeoutMs: 20000,
      typicalLatency: "3-10s",
      notes: "Token exchange and bulky property reads are the slow path.",
    },
    smoke: {
      id: "api-ura",
      name: "URA development charges",
      layer: "api",
      authRequired: true,
      releaseBlocking: true,
      tool: "sg_ura_dev_charges",
      arguments: {
        format: "json",
      },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises the authenticated URA runtime path without relying on placeholder data."],
    },
  },
  {
    api: "LTA DataMall",
    classification: "live_authenticated",
    authRequired: true,
    envVars: ["SG_API_LTA_KEY"],
    keystoreKeys: ["lta"],
    productionUrl: "https://datamall2.mytransport.sg/ltaodataservice",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_lta_bus_arrivals",
    dependentFamilies: ["LTA"],
    notes: [
      "LTA uses a header-based API key for live transport data.",
      "Operational transport workflows rely on the same authenticated runtime path.",
    ],
    healthNotes: [
      "Probed through the live LTA runtime client instead of an unauthenticated URL fetch.",
      "Release readiness fails if realtime transport checks cannot return live records.",
    ],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "0.5-2s",
      notes: "Realtime endpoints are fast when authenticated.",
    },
    smoke: {
      id: "api-lta",
      name: "LTA bus arrivals",
      layer: "api",
      authRequired: true,
      releaseBlocking: true,
      tool: "sg_lta_bus_arrivals",
      arguments: {
        busStopCode: "83139",
        format: "json",
      },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises a concrete realtime LTA endpoint with a stable bus stop code."],
    },
  },
  {
    api: "data.gov.sg datastore",
    classification: "shared_datagov_datastore",
    authRequired: false,
    envVars: [],
    keystoreKeys: [],
    productionUrl: "https://data.gov.sg/api/action/datastore_search",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_hdb_resale_prices",
    dependentFamilies: DATAGOV_DATASTORE_FAMILIES,
    notes: [
      "These curated families inherit the shared data.gov.sg datastore contract.",
      "Release validation should exercise at least one representative datastore-backed family.",
    ],
    healthNotes: [
      "Probed through a live HDB datastore-backed client call.",
      "Coverage notes enumerate every public family that shares the same datastore runtime path.",
    ],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "1-5s",
      notes: "Dataset size and data.gov.sg load dominate latency for datastore reads.",
    },
    smoke: {
      id: "api-datagov-datastore",
      name: "data.gov.sg datastore family",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_hdb_resale_prices",
      arguments: {
        town: "Bedok",
        flatType: "4 ROOM",
        limit: 1,
        format: "json",
      },
      expectation: { kind: "records_non_empty" },
      notes: ["Represents the shared datastore contract used by HDB and other public families."],
    },
  },
  {
    api: "data.gov.sg file downloads",
    classification: "shared_file_download",
    authRequired: false,
    envVars: [],
    keystoreKeys: [],
    productionUrl: "https://api-open.data.gov.sg/v1/public/api/datasets/{datasetId}/poll-download",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_boa_architecture_firms",
    dependentFamilies: DATAGOV_FILE_DOWNLOAD_FAMILIES,
    notes: [
      "These curated families inherit the shared official file-download path behind data.gov.sg.",
      "Release validation should exercise at least one representative file-download family.",
    ],
    healthNotes: [
      "Probed through a live BOA file-download client call.",
      "Coverage notes enumerate every public family that shares the same download runtime path.",
    ],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "1-5s",
      notes: "Download polling and CSV or GeoJSON parsing dominate latency for file-backed families.",
    },
    smoke: {
      id: "api-datagov-download",
      name: "data.gov.sg file-download family",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_boa_architecture_firms",
      arguments: {
        firmName: "DP ARCHITECTS PTE LTD",
        limit: 1,
        format: "json",
      },
      expectation: { kind: "records_non_empty" },
      notes: ["Represents the shared file-download contract used by BOA, HSA, HLB, PA, and other daily directories."],
    },
  },
  {
    api: "NEA",
    classification: "live_public",
    authRequired: false,
    envVars: [],
    keystoreKeys: [],
    productionUrl: "https://api-open.data.gov.sg/v2/real-time/api",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_nea_forecast_2hr",
    dependentFamilies: ["NEA"],
    notes: [
      "NEA runtime access is live-only and public.",
      "Operational environment workflows rely on the same realtime runtime path.",
    ],
    healthNotes: [
      "Probed through the live NEA runtime client rather than a generic URL fetch.",
      "Release readiness fails if realtime environment checks cannot return live records.",
    ],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "0.5-2s",
      notes: "Weather endpoints are typically responsive.",
    },
    smoke: {
      id: "api-nea",
      name: "NEA forecast",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_nea_forecast_2hr",
      arguments: {
        area: "Tampines",
        format: "json",
      },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises the live environment path with a stable planning area."],
    },
  },
  {
    api: "Government RSS Feeds",
    classification: "live_public",
    authRequired: false,
    envVars: [],
    keystoreKeys: [],
    productionUrl: "https://www.weather.gov.sg/files/rss/rss2HrForecast.xml",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_gov_feed_items",
    dependentFamilies: GOV_FEED_FAMILIES,
    notes: [
      "This surface aggregates direct official non-data.gov.sg feed contracts from NEA, weather.gov.sg, SFA, MPA, NHB, and URA newsroom listings.",
      "Feeds are parsed through bounded normalization with stream-level rollback controls.",
    ],
    healthNotes: [
      "Probed through the live govfeeds runtime client on a stable stream with real upstream records.",
      "Release readiness fails if official feed ingestion can no longer return normalized records.",
    ],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "1-6s",
      notes: "Feed and listing-page fetches are usually responsive but can vary with upstream publishing infrastructure.",
    },
    smoke: {
      id: "api-govfeeds",
      name: "Government feeds stream",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_gov_feed_items",
      arguments: {
        feedId: "weather_2hr_forecast",
        limit: 1,
        format: "json",
      },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises the live official-feed ingestion path with a high-availability stream."],
    },
  },
] as const;

export const LIVE_WORKFLOW_SMOKE_CASES: readonly SmokeCase[] = [
  {
    id: "workflow-business",
    name: "Business dossier workflow",
    layer: "workflow",
    authRequired: false,
    releaseBlocking: true,
    tool: "sg_business_dossier",
    arguments: {
      entityName: "DP ARCHITECTS PTE LTD",
      modules: ["acra", "boa"],
      sectorHints: ["architecture"],
      format: "json",
    },
    expectation: { kind: "brief_artifact", title: "Business Dossier", minimumProvenanceCount: 1 },
    notes: ["Represents a live diligence workflow over registry and architecture sources."],
  },
  {
    id: "workflow-property",
    name: "Property brief workflow",
    layer: "workflow",
    authRequired: true,
    releaseBlocking: true,
    tool: "sg_property_brief",
    arguments: {
      planningArea: "Bedok",
      includeTransport: true,
      includeEnvironment: true,
      format: "json",
    },
    expectation: { kind: "brief_artifact", title: "Property Brief", minimumProvenanceCount: 2 },
    notes: ["Represents a live cross-source property workflow with market, transport, and environment context."],
  },
  {
    id: "workflow-macro",
    name: "Macro brief workflow",
    layer: "workflow",
    authRequired: false,
    releaseBlocking: true,
    tool: "sg_macro_brief",
    arguments: {
      currency: "USD",
      format: "json",
    },
    expectation: { kind: "brief_artifact", title: "Macro Brief", minimumProvenanceCount: 2 },
    notes: ["Represents a live macro workflow over MAS and validated SingStat tables."],
  },
  {
    id: "workflow-transport",
    name: "Transport brief workflow",
    layer: "workflow",
    authRequired: true,
    releaseBlocking: true,
    tool: "sg_transport_brief",
    arguments: {
      busStopCode: "83139",
      format: "json",
    },
    expectation: { kind: "brief_artifact", title: "Transport Brief", minimumProvenanceCount: 1 },
    notes: ["Represents a live operational workflow over LTA realtime data."],
  },
  {
    id: "workflow-environment",
    name: "Environment brief workflow",
    layer: "workflow",
    authRequired: false,
    releaseBlocking: true,
    tool: "sg_environment_brief",
    arguments: {
      area: "Tampines",
      region: "East",
      format: "json",
    },
    expectation: { kind: "brief_artifact", title: "Environment Brief", minimumProvenanceCount: 1 },
    notes: ["Represents a live operational workflow over NEA realtime data."],
  },
  {
    id: "workflow-civic",
    name: "Civic discovery flow",
    layer: "workflow",
    authRequired: true,
    releaseBlocking: true,
    tool: "sg_query",
    arguments: {
      query: "Find a community club near 560123",
      mode: "execute",
      format: "json",
    },
    expectation: { kind: "query_completed", workflow: "civic_discovery" },
    notes: ["Represents a live civic and geospatial flow that resolves location then searches a bounded directory."],
  },
] as const;

export const RELEASE_BLOCKING_COMMANDS = [
  "npm run verify",
  "npm run test:smoke:live",
  "npm run test:smoke:packaging",
] as const;
