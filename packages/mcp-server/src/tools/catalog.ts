import type { ToolCatalogEntry } from "./tool-definition.js";
import { toToolCatalogEntry } from "./tool-definition.js";
import { ALL_TOOL_DEFINITIONS } from "./tool-set.js";
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

export type RuntimeCatalog = Readonly<Record<string, unknown>>;

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
    readonly evidence: string;
    readonly status: "within_slo" | "warning" | "breach";
    readonly notes: readonly string[];
  }[];
};

export type BenchmarkWorkflowProfile = {
  readonly workflow: string;
  readonly primaryCacheTier: string;
  readonly freshnessTarget: string;
  readonly evidence: string;
  readonly notes: readonly string[];
};

export type TransportReliabilitySourceProfile = {
  readonly sourceTool: string;
  readonly source: string;
  readonly surface: string;
  readonly authRequired: boolean;
  readonly coverage: string;
  readonly freshnessEvidence: string;
};

export const TOOL_CATALOG: readonly ToolCatalogEntry[] = ALL_TOOL_DEFINITIONS.map(toToolCatalogEntry);

export const API_CATALOG: readonly ApiCatalogEntry[] = [
  {
    name: "Swee Pulse",
    description: "Source-backed Singapore mobility, weather, source-health, and deterministic explain signals.",
    tools: ["swee_pulse_snapshot", "swee_pulse_mobility", "swee_pulse_weather", "swee_pulse_explain"],
    authRequired: false,
    rateLimit: "bounded local gateway policy",
    positioning: "Primary app-facing city signal interface.",
    preferredInterface: "swee_pulse_snapshot",
    scopeNotes: ["AI is optional and explain-only; Pulse signals are deterministic transformations of source records."],
  },
  {
    name: "Swee Shield",
    description: "Policy decisions, audit lookup, replay metadata, approval queue, policy simulation, and MCP poisoning scanner warnings.",
    tools: [
      "swee_shield_audit_lookup",
      "swee_shield_scan_tools",
      "swee_shield_approval_list",
      "swee_shield_approval_decide",
      "swee_shield_policy_simulate",
    ],
    authRequired: false,
    rateLimit: "local SQLite audit and approval stores",
    positioning: "Policy and audit layer for every REST and MCP tool invocation.",
    preferredInterface: "swee_shield_audit_lookup",
  },
  {
    name: "Splunk Shield Proxy",
    description: "Least-privilege Splunk MCP proxy tools governed by Swee Shield policy, audit, and runtime output defense.",
    tools: ["splunk_search", "splunk_list_indexes", "splunk_list_saved_searches", "swee_shield_splunk_investigation_pack"],
    authRequired: true,
    rateLimit: "bounded local gateway policy plus upstream Splunk RBAC",
    positioning: "Security-track proxy surface for governed agent access to Splunk data.",
    preferredInterface: "swee_shield_splunk_investigation_pack",
    scopeNotes: [
      "Requires SPLUNK_MCP_URL and SPLUNK_MCP_TOKEN or a splunk_mcp keystore entry for live mode.",
      "Mock investigation mode, policy simulation, approval queue, and red-team corpus are local and token-free.",
    ],
  },
  {
    name: "Mobility Sources",
    description: "Raw LTA and transport-adjacent source adapters.",
    tools: [
      "sg_lta_bus_arrivals",
      "sg_lta_train_alerts",
      "sg_lta_traffic_incidents",
      "sg_lta_road_works",
      "sg_lta_road_openings",
      "sg_lta_traffic_images",
      "sg_lta_carpark_availability",
      "sg_lta_taxi_availability",
      "sg_onemap_geocode",
      "sg_onemap_reverse_geocode",
      "sg_onemap_route",
    ],
    authRequired: true,
    rateLimit: "source-specific cache tiers",
    positioning: "Raw records behind Swee Pulse mobility signals.",
  },
  {
    name: "Weather Sources",
    description: "Raw NEA forecast, air-quality, and rainfall source adapters.",
    tools: ["sg_nea_forecast_2hr", "sg_nea_air_quality", "sg_nea_rainfall"],
    authRequired: false,
    rateLimit: "realtime cache tier",
    positioning: "Raw records behind Swee Pulse weather signals.",
  },
  {
    name: "Singapore Public Data Sources",
    description: "Reusable Singapore public-data adapters retained after CDD pruning.",
    tools: ALL_TOOL_DEFINITIONS
      .map((tool) => tool.name)
      .filter((name) => name.startsWith("sg_") && !name.includes("business_dossier") && !name.includes("cdd")),
    authRequired: false,
    rateLimit: "source-specific cache tiers",
    positioning: "Direct source-adapter surface for advanced callers.",
  },
  {
    name: "Operations",
    description: "Health, cache, config, key, trace, and request lookup tools.",
    tools: ["sg_health_check", "sg_cache_stats", "sg_cache_clear", "sg_key_set", "sg_key_list", "sg_key_delete", "sg_config_get", "sg_config_set", "sg_trace_lookup", "sg_request_lookup"],
    authRequired: false,
    rateLimit: "local operations policy",
    positioning: "Runtime diagnostics and local operator controls.",
  },
];

export const WORKFLOW_CATALOG: readonly WorkflowCatalogEntry[] = [
  {
    id: "pulse_snapshot",
    name: "Swee Pulse Snapshot",
    intent: "Summarize current Singapore mobility and weather signals with source freshness and gaps.",
    entrypoints: [{ tool: "swee_pulse_snapshot", input: { focus: "all" } }],
    fallbackTools: ["swee_pulse_mobility", "swee_pulse_weather"],
    blockerFields: ["sourceHealth", "gaps"],
    outputShapeVersion: "pulse-snapshot/v1",
    outputShapeNotes: ["Signals include provenance, freshness, gaps, and recommended actions."],
  },
  {
    id: "shield_audit_review",
    name: "Swee Shield Audit Review",
    intent: "Inspect policy decisions, denied calls, and replay metadata for recent tool invocations.",
    entrypoints: [{ tool: "swee_shield_audit_lookup", input: { limit: 25 } }],
    fallbackTools: ["swee_shield_scan_tools", "swee_shield_approval_list", "swee_shield_policy_simulate"],
    blockerFields: ["auditId", "traceId"],
    outputShapeVersion: "shield-audit/v1",
  },
  {
    id: "splunk_investigation_pack",
    name: "Splunk Incident Investigation Pack",
    intent: "Run bounded Shield-governed Splunk searches, summarize timeline evidence, surface redaction findings, and point analysts to next checks.",
    entrypoints: [{ tool: "swee_shield_splunk_investigation_pack", input: { question: "Investigate recent failed login activity", mode: "mock", limit: 20 } }],
    requiredInputs: ["question"],
    authPrerequisites: ["SPLUNK_MCP_URL and SPLUNK_MCP_TOKEN or splunk_mcp keystore entry for live mode"],
    fallbackTools: ["swee_shield_policy_simulate", "swee_shield_audit_lookup", "swee_shield_approval_list"],
    continuationTools: ["splunk_search", "swee_shield_audit_lookup", "swee_shield_approval_decide"],
    blockerFields: ["approvalId", "auditId", "runtimeFindings", "outputHash", "rawOutputHash"],
    continuationHints: ["Use mock mode for token-free demos; use live mode only after configuring Splunk MCP auth and allowed indexes."],
    outputShapeVersion: "swee-shield-splunk-investigation/v1",
    outputShapeNotes: ["Searches are bounded; event text may be redacted or neutralized before downstream agent use."],
  },
  {
    id: "source_adapter_lookup",
    name: "Raw Source Adapter Lookup",
    intent: "Call Singapore public-data source adapters directly when exact structured inputs are known.",
    entrypoints: [{ tool: "sg_datagov_search", input: { query: "traffic" } }],
    fallbackTools: ["sg_nea_forecast_2hr", "sg_lta_traffic_incidents", "sg_singstat_search"],
    continuationHints: ["Prefer Pulse tools for app-level city signals."],
  },
];

export const RECIPE_CATALOG: readonly RecipeCatalogEntry[] = [
  {
    id: "pulse_overview",
    name: "Pulse Overview",
    goal: "Generate a source-backed mobility and weather overview.",
    prompt: "Show the current Swee Pulse snapshot for Singapore.",
    preferredEntrypoint: { tool: "swee_pulse_snapshot", input: { focus: "all" } },
    fallbackTools: ["swee_pulse_mobility", "swee_pulse_weather"],
    notes: ["No AI key is required."],
    blockerFields: ["sourceHealth", "gaps"],
  },
  {
    id: "shield_recent_audit",
    name: "Recent Shield Audit",
    goal: "Review recent policy decisions and replay metadata.",
    prompt: "Show recent Swee Shield audit rows.",
    preferredEntrypoint: { tool: "swee_shield_audit_lookup", input: { limit: 25 } },
    fallbackTools: ["swee_shield_scan_tools", "swee_shield_approval_list", "swee_shield_policy_simulate"],
    notes: ["Audit records redact secrets and store hashes."],
    blockerFields: ["auditId", "traceId"],
  },
  {
    id: "splunk_investigation_pack",
    name: "Splunk Investigation Pack",
    goal: "Produce a governed incident investigation pack with timeline, hashes, redaction findings, policy decisions, and next analyst checks.",
    prompt: "Build a Swee Shield Splunk investigation pack for recent failed login activity.",
    preferredEntrypoint: {
      tool: "swee_shield_splunk_investigation_pack",
      input: { question: "Investigate recent failed login activity", mode: "mock", limit: 20 },
    },
    fallbackTools: ["swee_shield_policy_simulate", "swee_shield_audit_lookup", "swee_shield_approval_list"],
    notes: ["Mock mode is token-free and synthetic; live mode requires Splunk MCP credentials and upstream RBAC."],
    requiredInputs: ["question"],
    authPrerequisites: ["Splunk MCP credentials for live mode"],
    continuationTools: ["splunk_search", "swee_shield_audit_lookup", "swee_shield_approval_decide"],
    continuationHints: ["Inspect MCP resources under swee://shield/audits/{id} before rerunning broad searches."],
    blockerFields: ["approvalId", "runtimeFindings", "outputHash", "rawOutputHash"],
    outputShapeVersion: "swee-shield-splunk-investigation/v1",
  },
];

export const RUNTIME_CATALOG: RuntimeCatalog = {
  schemaVersion: "swee-runtime/v1",
  scope: "Policy-governed Singapore public-data source adapters, city signals, and Shield-governed Splunk MCP proxy tools",
  toolsetProfiles: TOOLSET_PROFILE_CATALOG,
  shieldModes: ["observe", "enforce", "kiasu"],
  pulseContract: "Signals are deterministic, source-backed, and include freshness, provenance, gaps, and recommended actions.",
  aiPosture: "Optional explain-only AI; core data and signal severity are deterministic.",
};

export const PLAYBOOK_CATALOG: readonly PlaybookCatalogEntry[] = [
  {
    id: "city_ops",
    name: "City Operations Desk",
    persona: "Operator watching Singapore mobility and weather disruptions.",
    jobsToBeDone: [
      "Identify watch-level and disrupted city signals.",
      "Open source health and freshness gaps before acting.",
      "Review Shield audit rows for policy decisions.",
    ],
    recommendedResources: ["sg://workflows", "sg://runtime"],
    primaryWorkflows: ["Swee Pulse Snapshot", "Swee Shield Audit Review", "Splunk Incident Investigation Pack"],
    starterPrompts: ["Show current Pulse signals", "Show recent Shield denials", "Build a mock Splunk investigation pack"],
    directTools: ["swee_pulse_snapshot", "swee_shield_audit_lookup", "swee_shield_splunk_investigation_pack"],
    notes: ["Treat Pulse as an operator signal layer, not an official emergency instruction channel."],
  },
  {
    id: "security_analyst",
    name: "Security Analyst Desk",
    persona: "Analyst investigating Splunk-backed incidents through policy-governed agent tools.",
    jobsToBeDone: [
      "Run bounded investigation packs before ad hoc SPL.",
      "Review Shield audit hashes and runtime findings before trusting agent output.",
      "Approve or reject broad Splunk searches with recorded reviewer context.",
    ],
    recommendedResources: ["swee://shield/redteam/corpus", "swee://shield/audits/{auditId}", "sg://workflows"],
    primaryWorkflows: ["Splunk Incident Investigation Pack", "Swee Shield Audit Review"],
    starterPrompts: ["Build a mock Splunk investigation pack", "Simulate this SPL policy decision", "Show pending Shield approvals"],
    directTools: ["swee_shield_splunk_investigation_pack", "swee_shield_policy_simulate", "swee_shield_approval_list"],
    notes: ["Mock mode is synthetic; live Splunk evidence remains governed by allowlists, approval mode, Shield audit, and runtime redaction."],
  },
];

export const BENCHMARK_EVIDENCE_SNAPSHOT: BenchmarkEvidenceSnapshot = {
  schemaVersion: "2.0",
  generatedAt: "2026-05-22T00:00:00.000Z",
  source: "repository-baseline",
  commitSha: "local",
  runUrl: null,
  checks: [
    { name: "npm run build", status: "passed", notes: "TypeScript build gate for Swee SG runtime." },
    { name: "pulse contract tests", status: "passed", notes: "Shared signal/freshness contract coverage." },
  ],
  sloMeasurements: [
    {
      workflow: "Swee Pulse Snapshot",
      availabilityPct: 99,
      latencyP50Ms: 500,
      latencyP95Ms: 2500,
      freshnessCompletenessPct: 90,
      measurementWindow: "repository baseline",
      evidence: "local deterministic tests and source-adapter health checks",
      status: "within_slo",
      notes: ["Live source availability depends on upstream agencies and configured credentials."],
    },
  ],
};

export const BENCHMARK_CATALOG = {
  schemaVersion: "swee-benchmarks/v1",
  workflows: ["Swee Pulse Snapshot", "Swee Pulse Mobility", "Transport Reliability Benchmark", "Swee Shield Audit Review", "Splunk Incident Investigation Pack"],
  workflowProfiles: [
    {
      workflow: "Swee Pulse Snapshot",
      primaryCacheTier: "REALTIME + STATIC",
      freshnessTarget: "15 minutes for weather and live mobility signals where upstreams provide timestamps",
      evidence: "pulse aggregator tests and gateway smoke checks",
      notes: ["Source freshness is surfaced per signal instead of hidden behind a generated summary."],
    },
    {
      workflow: "Swee Pulse Mobility",
      primaryCacheTier: "REALTIME",
      freshnessTarget: "15 minutes for LTA and data.gov.sg transport sources where upstream timestamps are available",
      evidence: "Pulse mobility aggregator tests and LTA adapter metadata",
      notes: ["Road works and road openings are emitted as source-backed transport signals, not only hidden coverage rows."],
    },
    {
      workflow: "Transport Reliability Benchmark",
      primaryCacheTier: "REALTIME",
      freshnessTarget: "Show observedAt, upstream timestamp or explicit missing-timestamp limits for every checked transport source",
      evidence: "generated public benchmark transportReliability.sourceChecks",
      notes: ["Benchmark evidence is coverage proof for civic-hacker demos, not an official operational status claim."],
    },
    {
      workflow: "Swee Shield Audit Review",
      primaryCacheTier: "LOCAL SQLITE",
      freshnessTarget: "Immediate write on every gateway and MCP tool invocation",
      evidence: "audit-store persistence and enforcement tests",
      notes: ["Replay metadata stores sanitized payloads and content hashes."],
    },
    {
      workflow: "Splunk Incident Investigation Pack",
      primaryCacheTier: "LOCAL SQLITE + SPLUNK MCP",
      freshnessTarget: "Mock mode is deterministic; live mode inherits explicit earliest/latest bounds and upstream Splunk freshness",
      evidence: "Splunk proxy policy simulator, approval queue, runtime scanner, and investigation-pack tests",
      notes: ["Live Splunk credential availability is not required for policy simulation, approval, mock packs, or audit resource inspection."],
    },
  ] satisfies readonly BenchmarkWorkflowProfile[],
  transportReliabilitySources: [
    {
      sourceTool: "sg_lta_traffic_incidents",
      source: "LTA DataMall",
      surface: "Swee Pulse mobility signal + source health",
      authRequired: true,
      coverage: "Network-wide traffic incident rows.",
      freshnessEvidence: "ObservedAt is retained; missing upstream row timestamps stay visible as a confidence limit.",
    },
    {
      sourceTool: "sg_lta_train_alerts",
      source: "LTA DataMall",
      surface: "Swee Pulse mobility signal + source health",
      authRequired: true,
      coverage: "Network-wide train service alerts and operator messages.",
      freshnessEvidence: "Operator message createdDate is used when present.",
    },
    {
      sourceTool: "sg_lta_road_works",
      source: "LTA DataMall",
      surface: "Swee Pulse mobility signal + source health",
      authRequired: true,
      coverage: "Network-wide road-work events with start/end timing.",
      freshnessEvidence: "Event timing is retained as upstream timing context.",
    },
    {
      sourceTool: "sg_lta_road_openings",
      source: "LTA DataMall",
      surface: "Swee Pulse mobility signal + source health",
      authRequired: true,
      coverage: "Network-wide road-opening events with start/end timing.",
      freshnessEvidence: "Event timing is retained as upstream timing context.",
    },
    {
      sourceTool: "sg_lta_traffic_images",
      source: "data.gov.sg transport feed",
      surface: "Swee Pulse source health",
      authRequired: false,
      coverage: "Traffic camera image references and camera timestamps.",
      freshnessEvidence: "Camera timestamps drive freshness where data.gov.sg returns them.",
    },
  ] satisfies readonly TransportReliabilitySourceProfile[],
  latestEvidenceSnapshot: BENCHMARK_EVIDENCE_SNAPSHOT,
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
  shieldRedteamCorpus: "swee://shield/redteam/corpus",
  shieldAudits: "swee://shield/audits",
  shieldApprovals: "swee://shield/approvals",
  mapPreviewUi: "ui://sg/map-preview",
} as const;
