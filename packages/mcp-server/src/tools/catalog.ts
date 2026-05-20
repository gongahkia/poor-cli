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

export const API_CATALOG: readonly ApiCatalogEntry[] = [
  {
    name: "CDD Query",
    description: "Goal-shaped company and sector diligence prompts routed through the bounded CDD orchestrator path.",
    tools: ["sg_query"],
    authRequired: false,
    rateLimit: "local planner",
    positioning: "Preferred entrypoint for natural-language CDD searches.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "CDD-only: non-company public-data prompts return unsupported with a CDD-specific suggestion.",
      "Use direct tools only as low-level compatibility APIs when the caller already has exact structured parameters.",
    ],
  },
  {
    name: "Business Dossier",
    description: "Low-level compatibility artifact for Singapore company and sector dossiers; product flows should use the CDD orchestrator.",
    tools: ["sg_business_dossier"],
    authRequired: false,
    rateLimit: "bounded by selected modules",
    positioning: "Advanced compatibility API behind the orchestrated CDD report flow.",
    preferredInterface: "sg_query",
  },
  {
    name: "ACRA",
    description: "Corporate-entity identity lookup for Singapore company/UEN matching.",
    tools: ["sg_acra_entities"],
    authRequired: false,
    rateLimit: "data.gov.sg-backed cache tier",
    positioning: "Core identity evidence used by the CDD orchestrator for every company CDD run.",
    preferredInterface: "sg_query",
  },
  {
    name: "BCA",
    description: "Builder and contractor registry enrichment for construction-sector diligence.",
    tools: ["sg_bca_licensed_builders", "sg_bca_registered_contractors"],
    authRequired: false,
    rateLimit: "data.gov.sg-backed cache tier",
    positioning: "Sector registry evidence automatically used by the orchestrator when construction signals are present.",
    preferredInterface: "sg_query",
  },
  {
    name: "BOA",
    description: "Board of Architects register enrichment for architecture firms and architects.",
    tools: ["sg_boa_architects", "sg_boa_architecture_firms"],
    authRequired: false,
    rateLimit: "static registry cache tier",
    positioning: "Sector registry evidence automatically used by the orchestrator when architecture signals are present.",
    preferredInterface: "sg_query",
  },
  {
    name: "CEA",
    description: "Estate-agent and salesperson registration evidence.",
    tools: ["sg_cea_salespersons"],
    authRequired: false,
    rateLimit: "data.gov.sg-backed cache tier",
    positioning: "CDD enrichment automatically used by the orchestrator when real-estate signals are present.",
    preferredInterface: "sg_query",
  },
  {
    name: "GeBIZ",
    description: "Public tender and award evidence for procurement-facing counterparties.",
    tools: ["sg_gebiz_tenders"],
    authRequired: false,
    rateLimit: "public source cache tier",
    positioning: "Procurement evidence automatically used by the orchestrator when procurement exposure signals are present.",
    preferredInterface: "sg_query",
  },
  {
    name: "HSA",
    description: "Health-product licensee and pharmacy registry evidence.",
    tools: ["sg_hsa_licensed_pharmacies", "sg_hsa_health_product_licensees"],
    authRequired: false,
    rateLimit: "static registry cache tier",
    positioning: "Healthcare-sector enrichment automatically used by the orchestrator when healthcare signals are present.",
    preferredInterface: "sg_query",
  },
  {
    name: "HLB",
    description: "Hotel Licensing Board hotel and keeper evidence.",
    tools: ["sg_hlb_hotels"],
    authRequired: false,
    rateLimit: "static registry cache tier",
    positioning: "Hospitality-sector enrichment automatically used by the orchestrator when hospitality signals are present.",
    preferredInterface: "sg_query",
  },
  {
    name: "External Diligence",
    description: "Supplemental analyst-review signals for sanctions links, OpenCorporates links, adverse-media hints, and relationship graphs.",
    tools: ["sg_sanctions_screen", "sg_opencorporates_links", "sg_adverse_media_lite", "sg_relationship_graph"],
    authRequired: false,
    rateLimit: "provider-dependent",
    positioning: "Supplemental evidence used by the orchestrator; not an automated compliance decision.",
    preferredInterface: "sg_query",
  },
  {
    name: "Operations",
    description: "Health, cache, key, config, trace, and request lookup tools for running the CDD product safely.",
    tools: [
      "sg_health_check",
      "sg_cache_stats",
      "sg_cache_clear",
      "sg_key_set",
      "sg_key_list",
      "sg_key_delete",
      "sg_config_get",
      "sg_config_set",
      "sg_trace_lookup",
      "sg_request_lookup",
    ],
    authRequired: false,
    rateLimit: "local runtime",
    positioning: "Operator surface, not a product CTA.",
  },
];

export const TOOL_CATALOG: readonly ToolCatalogEntry[] = ALL_TOOL_DEFINITIONS.map(toToolCatalogEntry);

export const WORKFLOW_CATALOG: readonly WorkflowCatalogEntry[] = [
  {
    id: "company_cdd_report",
    name: "Company CDD Report",
    intent: "Search a Singapore company or UEN and produce a cited CDD dossier for analyst review.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Business dossier for DP Architects", mode: "execute" } },
    ],
    requiredInputs: ["entityName or uen"],
    blockerFields: ["entityName", "uen", "registrationNo"],
    fallbackTools: ["sg_acra_entities", "sg_bca_registered_contractors", "sg_cea_salespersons"],
    continuationTools: ["sg_gebiz_tenders", "sg_sanctions_screen", "sg_opencorporates_links"],
    continuationHints: [
      "Use the AI memo and report builder to produce a cited summary with evidence-bound claims.",
      "Treat web presence and people discovery as analyst-review evidence, not registry facts.",
    ],
    outputShapeVersion: "business-dossier/v1",
    outputShapeNotes: [
      "Every summary claim should remain tied to evidence, provenance, freshness, gaps, and limits.",
      "Exports should preserve the manifest and selected report sections.",
    ],
  },
  {
    id: "architecture_firm_diligence",
    name: "Architecture Firm Diligence",
    intent: "Enrich an entity dossier with BOA, ACRA, and procurement evidence for architecture-firm review.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Architecture firm diligence for DP Architects", mode: "execute" } },
    ],
    requiredInputs: ["entityName or uen"],
    fallbackTools: ["sg_boa_architecture_firms", "sg_boa_architects", "sg_acra_entities"],
    continuationTools: ["sg_gebiz_tenders"],
    outputShapeVersion: "business-dossier/v1",
  },
  {
    id: "healthcare_supplier_diligence",
    name: "Healthcare Supplier Diligence",
    intent: "Enrich an entity dossier with HSA and procurement evidence for healthcare-supplier review.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Healthcare supplier diligence for a pharmacy operator", mode: "execute" } },
    ],
    requiredInputs: ["entityName or uen"],
    fallbackTools: ["sg_hsa_health_product_licensees", "sg_hsa_licensed_pharmacies", "sg_acra_entities"],
    continuationTools: ["sg_gebiz_tenders"],
    outputShapeVersion: "business-dossier/v1",
  },
  {
    id: "hotel_operator_lookup",
    name: "Hotel Operator Lookup",
    intent: "Enrich an entity dossier with HLB hotel and keeper evidence.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Hotel operator lookup for a Singapore hotel", mode: "execute" } },
    ],
    requiredInputs: ["entityName or uen"],
    fallbackTools: ["sg_hlb_hotels", "sg_acra_entities"],
    continuationTools: ["sg_gebiz_tenders"],
    outputShapeVersion: "business-dossier/v1",
  },
];

export const RECIPE_CATALOG: readonly RecipeCatalogEntry[] = [
  {
    id: "business_due_diligence",
    name: "Business Due Diligence",
    goal: "Produce a cited CDD report draft from a Singapore company name, UEN, or registration identifier.",
    prompt: "Business dossier for DP Architects",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Business dossier for DP Architects", mode: "execute" },
    },
    fallbackTools: ["sg_business_dossier", "sg_acra_entities", "sg_bca_licensed_builders"],
    notes: [
      "Use this as the default recipe for company/UEN search.",
      "Keep conclusions framed as analyst-review findings, not pass/fail decisions.",
    ],
    requiredInputs: ["entityName or uen"],
    blockerFields: ["entityName", "uen", "registrationNo"],
    continuationTools: ["sg_gebiz_tenders", "sg_sanctions_screen", "sg_opencorporates_links", "sg_adverse_media_lite"],
    outputShapeVersion: "business-dossier/v1",
  },
  {
    id: "architecture_firm_diligence",
    name: "Architecture Firm Diligence",
    goal: "Check company identity plus BOA architecture-firm evidence.",
    prompt: "Architecture firm diligence for DP Architects",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Architecture firm diligence for DP Architects", mode: "execute" },
    },
    fallbackTools: ["sg_business_dossier", "sg_boa_architecture_firms", "sg_boa_architects"],
    notes: ["Use BOA matches as sector enrichment alongside ACRA identity evidence."],
    requiredInputs: ["entityName or uen"],
    continuationTools: ["sg_gebiz_tenders"],
    outputShapeVersion: "business-dossier/v1",
  },
  {
    id: "healthcare_supplier_diligence",
    name: "Healthcare Supplier Diligence",
    goal: "Check company identity plus HSA licensee/pharmacy evidence.",
    prompt: "Healthcare supplier diligence for a pharmacy operator",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Healthcare supplier diligence for a pharmacy operator", mode: "execute" },
    },
    fallbackTools: ["sg_business_dossier", "sg_hsa_health_product_licensees", "sg_hsa_licensed_pharmacies"],
    notes: ["Use HSA matches as sector enrichment; unresolved licenses should be shown as coverage gaps."],
    requiredInputs: ["entityName or uen"],
    continuationTools: ["sg_gebiz_tenders"],
    outputShapeVersion: "business-dossier/v1",
  },
  {
    id: "hotel_operator_lookup",
    name: "Hotel Operator Lookup",
    goal: "Check company identity plus HLB hotel and keeper evidence.",
    prompt: "Hotel operator lookup for a Singapore hotel",
    preferredEntrypoint: {
      tool: "sg_query",
      input: { query: "Hotel operator lookup for a Singapore hotel", mode: "execute" },
    },
    fallbackTools: ["sg_business_dossier", "sg_hlb_hotels"],
    notes: ["Use HLB matches as sector enrichment and preserve hotel/keeper attribution."],
    requiredInputs: ["entityName or uen"],
    continuationTools: ["sg_gebiz_tenders"],
    outputShapeVersion: "business-dossier/v1",
  },
];

export const RUNTIME_CATALOG: RuntimeCatalog = {
  scope: "CDD-only Singapore company and sector diligence",
  toolsetProfiles: TOOLSET_PROFILE_CATALOG,
  liveSurface: [
    {
      api: "CDD dossier",
      classification: "public-registry and supplemental analyst-review evidence",
      authRequired: false,
      probeMode: "workflow",
      productionUrl: "local MCP/runtime",
      representativeTool: "sg_query",
      releaseBlocking: true,
      coversFamilies: ["ACRA", "BCA", "BOA", "CEA", "GeBIZ", "HSA", "HLB", "External Diligence"],
      notes: ["Non-CDD public-data tools are intentionally not registered."],
    },
  ],
  authDependencies: [
    {
      api: "External Diligence",
      authRequired: false,
      envVars: ["OPENSANCTIONS_API_KEY", "OPENCORPORATES_API_TOKEN"],
      keystoreKeys: [],
      notes: ["Optional provider credentials can improve supplemental evidence coverage."],
    },
  ],
  sourceUseWarnings: [
    {
      api: "ACRA",
      observedAt: "2026-05-18",
      posture: "review_before_hosted_paid_use",
      termsUrls: [],
      docs: ["docs/acra-licensing-track.md", "docs/public-data-limits.md"],
      warnings: ["Confirm production redistribution terms before hosted commercial use."],
    },
    {
      api: "External Diligence",
      observedAt: "2026-05-18",
      posture: "review_before_hosted_paid_use",
      termsUrls: [],
      docs: ["docs/public-data-limits.md"],
      warnings: ["Supplemental web/media/person signals require analyst review and should not be treated as official registry facts."],
    },
  ],
  credentialSourceRules: [
    "Use sg_key_set only for provider credentials explicitly required by retained CDD integrations.",
    "Do not request OneMap, URA, LTA, or other removed public-data credentials for CDD-only workflows.",
  ],
  latency: {
    hardCapMs: 12000,
    targets: [
      { api: "CDD orchestrator", timeoutMs: 12000, typicalLatency: "ACRA-gated sector enrichment plus supplemental review and memo state", notes: "Product path for web, widgets, bulk, and report exports." },
      { api: "sg_query", timeoutMs: 12000, typicalLatency: "planner-only or orchestrated CDD execution", notes: "Unsupported non-CDD prompts should return quickly." },
    ],
  },
  cacheTiers: [
    { tier: "STATIC", ttlSeconds: 604800, usedBy: ["ACRA", "BCA", "BOA", "CEA", "HSA", "HLB"], rationale: "Registry data changes slower than interactive report review." },
    { tier: "SUPPLEMENTAL", ttlSeconds: 86400, usedBy: ["GeBIZ", "External Diligence"], rationale: "Procurement and web/media signals need fresher review." },
  ],
  rateLimits: [
    { api: "CDD dossier", maxTokens: 20, refillPerSecond: 2, effectiveRate: "bounded local workflow concurrency" },
  ],
  retryPolicy: {
    retryable: ["HTTP_5XX", "UPSTREAM_TIMEOUT", "RATE_LIMITED"],
    nonRetryable: ["VALIDATION_ERROR", "EMPTY_RESULT", "UNSUPPORTED_WORKFLOW"],
    backoffSeconds: [1, 2, 5],
    maxRetries: 2,
    respectsRetryAfter: true,
  },
  circuitBreaker: {
    threshold: 5,
    resetTimeoutSeconds: 60,
    states: ["closed", "open", "half_open"],
    note: "Breakers protect upstream registry and supplemental CDD calls.",
  },
  partialFailureSemantics: [
    "Dossiers may complete with gaps when optional sector or supplemental evidence fails.",
    "Claims in AI memos and exports must remain evidence-bound and cite available sources.",
  ],
  healthCoverage: [
    { api: "CDD dossier", coversFamilies: ["ACRA", "BCA", "CEA", "GeBIZ"], notes: ["Health is operational only; run representative dossier smoke tests before release."] },
  ],
  releaseReadiness: {
    blockingCommands: ["npm run build", "npm run test", "npm run verify", "npm run test:smoke:web"],
    requiredSmokeCases: [
      {
        name: "CDD dossier",
        tool: "sg_query",
        layer: "workflow",
        authRequired: false,
        releaseBlocking: true,
        arguments: { query: "Business dossier for DP Architects", mode: "execute" },
        expectation: { status: "completed_or_gapful", outputShapeVersion: "business-dossier/v1" },
        notes: ["Must preserve provenance, freshness, gaps, limits, and evidence records."],
      },
    ],
    failureSemantics: [
      "Unsupported non-CDD prompts should not fall through to broad public-data tools.",
      "Report exports must preserve selected sections and citations.",
    ],
    notes: ["This runtime catalog is intentionally narrower than historical Dude MCP releases."],
  },
  queryStatusContract: [
    { status: "planned", isError: false, notes: "A supported CDD plan was built but not executed." },
    { status: "completed", isError: false, notes: "All planned CDD steps completed, possibly with evidence gaps." },
    { status: "blocked", isError: false, notes: "CDD workflow needs a company/UEN or equivalent identifier." },
    { status: "unsupported", isError: false, notes: "Prompt is outside the CDD-only product surface." },
    { status: "failed", isError: true, notes: "A supported CDD step failed unexpectedly." },
  ],
};

export const PLAYBOOK_CATALOG: readonly PlaybookCatalogEntry[] = [
  {
    id: "business_opportunity_scan",
    name: "CDD Analyst Review",
    persona: "CDD analyst preparing a source-backed counterparty report.",
    jobsToBeDone: [
      "Search a Singapore company or UEN.",
      "Read the cited summary before inspecting raw evidence.",
      "Open citations and evidence-pack sections only when substantiation is needed.",
      "Export a PDF or DOCX report with selected CDD sections and preserved attribution.",
    ],
    recommendedResources: ["sg://recipes", "sg://runtime", "sg://benchmarks"],
    primaryWorkflows: ["Company CDD Report", "Architecture Firm Diligence", "Healthcare Supplier Diligence", "Hotel Operator Lookup"],
    starterPrompts: [
      "Business dossier for DP Architects",
      "Architecture firm diligence for DP Architects",
      "Healthcare supplier diligence for a pharmacy operator",
      "Hotel operator lookup for a Singapore hotel",
    ],
    directTools: [
      "sg_business_dossier",
      "sg_acra_entities",
      "sg_bca_registered_contractors",
      "sg_boa_architecture_firms",
      "sg_hsa_health_product_licensees",
      "sg_hlb_hotels",
      "sg_gebiz_tenders",
    ],
    notes: [
      "Workspace, bulk runs, watchlists, audit logs, and exports support the CDD workflow rather than competing with it.",
      "Supplemental web/person/media evidence should stay clearly labeled for analyst review.",
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

export const BENCHMARK_EVIDENCE_SNAPSHOT: BenchmarkEvidenceSnapshot = {
  schemaVersion: "2.0",
  generatedAt: "2026-05-18T00:00:00.000Z",
  source: "repository-baseline",
  commitSha: "local",
  runUrl: null,
  checks: [
    { name: "npm run build", status: "passed", notes: "Expected release gate for the CDD-only runtime." },
    { name: "npm run test", status: "skipped", notes: "Run in CI or local verification after fixture cleanup." },
    { name: "npm run verify", status: "skipped", notes: "Run before release after docs and catalog snapshots are regenerated." },
  ],
  sloMeasurements: [
    {
      workflow: "Company CDD Report",
      availabilityPct: 99,
      latencyP50Ms: 1200,
      latencyP95Ms: 5000,
      freshnessCompletenessPct: 100,
      measurementWindow: "rolling-7d target",
      status: "within_slo",
      evidence: "repository baseline",
      notes: ["CDD reports must preserve provenance, freshness, gaps, limits, and citations."],
    },
  ],
};

export const BENCHMARK_CATALOG = {
  summary: [
    "Benchmarks now focus on CDD report generation, evidence inspection, and export credibility.",
    "Non-CDD public-data workflows are intentionally excluded from product discovery.",
  ],
  workflowProfiles: [
    {
      workflow: "Company CDD Report",
      typicalColdPath: "1-5s with registry modules and supplemental evidence disabled or cached",
      typicalWarmPath: "<1s for cached registry records",
      primaryCacheTier: "STATIC + SUPPLEMENTAL",
      freshnessRule: "Report freshness must show upstream timestamps or observedAt values for every included evidence family.",
      notes: [
        "The cited summary is the primary user experience.",
        "The evidence pack and report manifest are mandatory for auditability.",
      ],
    },
  ],
  baselineSLOs: {
    measurementWindow: "rolling-7d",
    interpretation: [
      "Availability measures successful CDD dossier/report flow completion.",
      "Freshness completeness measures whether included report sections expose provenance and observed timestamps.",
    ],
    targets: [
      {
        workflow: "Company CDD Report",
        availabilityPct: 99,
        latencyP95Ms: 5000,
        freshnessCompletenessPct: 100,
      },
    ],
  },
  adoptionCheckpoints: [
    {
      name: "Search-to-report success",
      expectation: "A new user can search a company/UEN, read a cited summary, inspect evidence, and export PDF or DOCX.",
      evidence: "Use the web smoke flow and representative CDD orchestrator fixture.",
    },
    {
      name: "Unsupported scope clarity",
      expectation: "Non-CDD prompts return unsupported instead of silently routing into removed public-data tools.",
      evidence: "Use sg_query with a housing, transport, weather, or macro prompt.",
    },
  ],
  latestEvidenceSnapshot: BENCHMARK_EVIDENCE_SNAPSHOT,
  releaseBlockingChecks: [
    "A failing CDD dossier smoke blocks release.",
    "A report export missing selected sections, citations, provenance, freshness, gaps, limits, or manifest data blocks release.",
    "Any non-CDD tool reappearing in registered runtime discovery blocks release.",
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
