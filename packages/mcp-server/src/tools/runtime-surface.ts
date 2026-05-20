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
  "ACRA",
  "BCA",
  "CEA",
  "GeBIZ",
] as const;

export const DATAGOV_FILE_DOWNLOAD_FAMILIES = [
  "BOA",
  "HSA",
  "HLB",
] as const;

export const GOV_FEED_FAMILIES = [] as const;

export const LIVE_API_SURFACE: readonly LiveSurfaceDefinition[] = [
  {
    api: "data.gov.sg datastore",
    classification: "shared_datagov_datastore",
    authRequired: false,
    envVars: [],
    keystoreKeys: [],
    productionUrl: "https://data.gov.sg",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_acra_entities",
    dependentFamilies: [...DATAGOV_DATASTORE_FAMILIES],
    notes: ["CDD registry evidence uses bounded data.gov.sg-backed datasets where applicable."],
    healthNotes: ["Probed through ACRA entity lookup instead of removed public-data families."],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "1-5s",
      notes: "Cold reads depend on upstream download/cache state.",
    },
    smoke: {
      id: "api-cdd-datastore",
      name: "CDD datastore registry read",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_acra_entities",
      arguments: { entityName: "DP ARCHITECTS PTE LTD", format: "json" },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises the core company identity source path."],
    },
  },
  {
    api: "data.gov.sg file downloads",
    classification: "shared_file_download",
    authRequired: false,
    envVars: [],
    keystoreKeys: [],
    productionUrl: "https://data.gov.sg",
    probeMode: "runtime_client",
    releaseBlocking: true,
    representativeTool: "sg_boa_architecture_firms",
    dependentFamilies: [...DATAGOV_FILE_DOWNLOAD_FAMILIES],
    notes: ["CDD sector registries use official file-download sources where applicable."],
    healthNotes: ["Probed through BOA architecture-firm lookup."],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "1-5s",
      notes: "Official file downloads are cached and normalized before dossier use.",
    },
    smoke: {
      id: "api-cdd-file-download",
      name: "CDD file-download registry read",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_boa_architecture_firms",
      arguments: { firmName: "DP Architects", format: "json" },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises a retained sector registry path."],
    },
  },
  {
    api: "External Diligence",
    classification: "live_public",
    authRequired: false,
    envVars: ["OPENSANCTIONS_API_KEY", "OPENCORPORATES_API_TOKEN"],
    keystoreKeys: [],
    productionUrl: "provider-dependent",
    probeMode: "runtime_client",
    releaseBlocking: false,
    representativeTool: "sg_sanctions_screen",
    dependentFamilies: ["External Diligence"],
    notes: ["Supplemental evidence is analyst-review only and may depend on optional provider credentials."],
    healthNotes: ["Health check verifies runtime availability; source-specific credentials are optional."],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "0.5-5s",
      notes: "Latency depends on optional providers and cache state.",
    },
    smoke: {
      id: "api-external-diligence",
      name: "External diligence runtime readiness",
      layer: "api",
      authRequired: false,
      releaseBlocking: false,
      tool: "sg_sanctions_screen",
      arguments: { name: "DP ARCHITECTS PTE LTD", format: "json" },
      expectation: { kind: "records_non_empty", key: "records" },
      notes: ["Supplemental provider outputs are not official registry facts."],
    },
  },
] as const;

export const LIVE_WORKFLOW_SMOKE_CASES: readonly SmokeCase[] = [
  {
    id: "workflow-company-cdd",
    name: "Company CDD report",
    layer: "workflow",
    authRequired: false,
    releaseBlocking: true,
    tool: "sg_business_dossier",
    arguments: {
      entityName: "DP ARCHITECTS PTE LTD",
      modules: ["acra", "boa", "gebiz"],
      sectorHints: ["architecture", "procurement"],
      format: "json",
    },
    expectation: { kind: "brief_artifact", title: "Business Dossier", minimumProvenanceCount: 1 },
    notes: ["Represents the primary search-to-dossier CDD workflow."],
  },
  {
    id: "workflow-cdd-query",
    name: "CDD query workflow",
    layer: "workflow",
    authRequired: false,
    releaseBlocking: true,
    tool: "sg_query",
    arguments: {
      query: "Architecture firm diligence for DP Architects",
      mode: "execute",
      format: "json",
    },
    expectation: { kind: "query_completed", workflow: "architecture_firm_diligence" },
    notes: ["Proves sg_query routes only into retained CDD workflows."],
  },
] as const;

export const RELEASE_BLOCKING_COMMANDS = [
  "npm run build",
  "npm run test",
  "npm run verify",
  "npm run test:smoke:web",
] as const;
