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
    description: "Policy decisions, audit lookup, replay metadata, and MCP poisoning scanner warnings.",
    tools: ["swee_shield_audit_lookup", "swee_shield_scan_tools"],
    authRequired: false,
    rateLimit: "local SQLite audit store",
    positioning: "Policy and audit layer for every REST and MCP tool invocation.",
    preferredInterface: "swee_shield_audit_lookup",
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
    fallbackTools: ["swee_shield_scan_tools"],
    blockerFields: ["auditId", "traceId"],
    outputShapeVersion: "shield-audit/v1",
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
    fallbackTools: ["swee_shield_scan_tools"],
    notes: ["Audit records redact secrets and store hashes."],
    blockerFields: ["auditId", "traceId"],
  },
];

export const RUNTIME_CATALOG: RuntimeCatalog = {
  schemaVersion: "swee-runtime/v1",
  scope: "Policy-governed Singapore public-data source adapters and city signals",
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
    primaryWorkflows: ["Swee Pulse Snapshot", "Swee Shield Audit Review"],
    starterPrompts: ["Show current Pulse signals", "Show recent Shield denials"],
    directTools: ["swee_pulse_snapshot", "swee_shield_audit_lookup"],
    notes: ["Treat Pulse as an operator signal layer, not an official emergency instruction channel."],
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
  workflows: ["Swee Pulse Snapshot", "Swee Pulse Mobility", "Transport Reliability Benchmark", "Swee Shield Audit Review"],
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
  mapPreviewUi: "ui://sg/map-preview",
} as const;
