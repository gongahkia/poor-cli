export type LiveSurfaceClassification =
  | "live_public"
  | "live_authenticated"
  | "shared_datagov_datastore"
  | "shared_file_download";

export type SmokeExpectation =
  | Readonly<{ kind: "records_non_empty"; key?: "records" }>
  | Readonly<{ kind: "pulse_snapshot"; minimumSignalCount?: number }>
  | Readonly<{ kind: "shield_audit"; minimumRecordCount?: number }>;

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
    notes: ["Retained source adapters use bounded data.gov.sg-backed datasets where applicable."],
    healthNotes: ["Probed through ACRA entity lookup as a representative data.gov.sg datastore read."],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "1-5s",
      notes: "Cold reads depend on upstream download/cache state.",
    },
    smoke: {
      id: "api-datagov-datastore",
      name: "data.gov.sg datastore read",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_acra_entities",
      arguments: { entityName: "DP ARCHITECTS PTE LTD", format: "json" },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises a retained public-data source path."],
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
    notes: ["Retained sector registries use official file-download sources where applicable."],
    healthNotes: ["Probed through BOA architecture-firm lookup."],
    latency: {
      timeoutMs: 10000,
      typicalLatency: "1-5s",
      notes: "Official file downloads are cached and normalized before source-adapter responses.",
    },
    smoke: {
      id: "api-file-download",
      name: "file-download registry read",
      layer: "api",
      authRequired: false,
      releaseBlocking: true,
      tool: "sg_boa_architecture_firms",
      arguments: { firmName: "DP Architects", format: "json" },
      expectation: { kind: "records_non_empty" },
      notes: ["Exercises a retained sector registry path."],
    },
  },
] as const;

export const LIVE_WORKFLOW_SMOKE_CASES: readonly SmokeCase[] = [
  {
    id: "workflow-pulse-snapshot",
    name: "Swee Pulse Snapshot",
    layer: "workflow",
    authRequired: false,
    releaseBlocking: true,
    tool: "swee_pulse_snapshot",
    arguments: {
      focus: "all",
    },
    expectation: { kind: "pulse_snapshot" },
    notes: ["Represents the primary city signal workflow."],
  },
  {
    id: "workflow-shield-audit-review",
    name: "Swee Shield Audit Review",
    layer: "workflow",
    authRequired: false,
    releaseBlocking: true,
    tool: "swee_shield_audit_lookup",
    arguments: {
      limit: 25,
    },
    expectation: { kind: "shield_audit" },
    notes: ["Represents policy audit and replay inspection."],
  },
] as const;

export const RELEASE_BLOCKING_COMMANDS = [
  "npm run build",
  "npm run test",
  "npm run verify",
  "npm run test:smoke:web",
] as const;
