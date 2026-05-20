import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const { API_CATALOG, RECIPE_CATALOG, RUNTIME_CATALOG, TOOL_CATALOG, WORKFLOW_CATALOG } = await import(
  pathToFileURL(resolve(root, "packages/mcp-server/dist/tools/catalog.js")).href
);

const totalTools = TOOL_CATALOG.length;
const familyCount = API_CATALOG.length;
const routedFamilyCount = API_CATALOG.filter((api) => api.preferredInterface === "sg_query").length;
const routedFamilyLabel = `${routedFamilyCount} sg_query-routed CDD ${routedFamilyCount === 1 ? "family" : "families"}`;
const familyNames = API_CATALOG.map((api) => api.name);
const workflowNames = WORKFLOW_CATALOG.map((workflow) => workflow.name);
const recipeNames = RECIPE_CATALOG.map((recipe) => recipe.name);
const sgQuery = TOOL_CATALOG.find((tool) => tool.name === "sg_query");

if (sgQuery?.preferred !== true) {
  throw new Error("sg_query is no longer marked preferred in the built tool catalog.");
}

const readmeTarget = existsSync(resolve(root, "README2.md")) ? "README2.md" : "README.md";
const read = (path) => readFileSync(resolve(root, path), "utf8");
const ensureIncludes = (path, snippets) => {
  const text = read(path);
  for (const snippet of snippets) {
    if (!text.includes(snippet)) {
      throw new Error(`${path} is missing required snippet: ${snippet}`);
    }
  }
};

const ensureExcludes = (path, snippets) => {
  const text = read(path);
  for (const snippet of snippets) {
    if (text.includes(snippet)) {
      throw new Error(`${path} still includes stale snippet: ${snippet}`);
    }
  }
};

const ensureProductDocsUseOrchestratorPath = (paths) => {
  const prohibited = [
    {
      pattern: /POST\s+\/api\/v1\/sg_business_dossier/,
      message: "documents the direct dossier REST endpoint as a product entrypoint",
    },
    {
      pattern: /calls? .*\/api\/v1\/sg_business_dossier/i,
      message: "describes a product integration calling the direct dossier endpoint",
    },
    {
      pattern: /Company\/UEN CDD report\s*\|\s*`sg_business_dossier`/i,
      message: "routes company CDD reports directly to sg_business_dossier",
    },
  ];

  for (const path of paths) {
    const text = read(path);
    for (const { pattern, message } of prohibited) {
      if (pattern.test(text)) {
        throw new Error(`${path} ${message}. Use the CDD orchestrator path and describe sg_business_dossier as low-level compatibility.`);
      }
    }
  }
};

const cddCoreSnippets = [
  "Search a Singapore company or UEN. Get a cited CDD report for analyst review.",
  `${totalTools} \`sg_*\` tools total`,
  `${familyCount} CDD catalog families`,
  routedFamilyLabel,
  "sg_business_dossier",
  "sg_acra_entities",
  "sg_boa_architecture_firms",
  "sg_hsa_health_product_licensees",
  "sg_hlb_hotels",
  "sg_sanctions_screen",
  "sg://recipes",
  "sg://runtime",
  "sg://playbooks",
  "sg://benchmarks",
  "Report Builder",
  "PDF or DOCX",
];

const removedSurfaceSnippets = [
  "sg_property_brief",
  "sg_macro_brief",
  "sg_transport_brief",
  "sg_environment_brief",
  "sg_civic_brief",
  "sg_datagov_browse",
  "sg_singstat_browse",
  "sg_onemap_route",
  "Property Due Diligence",
  "Postal Route",
  "SingStat Drilldown",
  "HDB Rental Check",
  "Dataset Collection Browse",
];

ensureIncludes(readmeTarget, [
  ...cddCoreSnippets,
  "agent-builder-quickstart.md",
  "product-health.md",
  "Start Here For Builders",
  "examples/integration/basic-client.ts",
  "examples/integration/basic-client.py",
  "npm run test:smoke:profiles",
  ...familyNames,
  ...workflowNames,
]);
ensureExcludes(readmeTarget, removedSurfaceSnippets);

ensureIncludes("AGENTS.md", [
  "CDD-only",
  "CDD orchestrator",
  "low-level compatibility",
  "sg_query",
  "sg_business_dossier",
  "Evidence Pack",
  "Never invent CDD values",
]);
ensureExcludes("AGENTS.md", ["Housing Advisor", "sg_housing_affordability", "sg_grant_eligibility"]);

ensureIncludes("docs/architecture.md", [
  `${familyCount} CDD catalog families`,
  "company CDD report",
  "architecture firm diligence",
  "healthcare supplier diligence",
  "hotel operator lookup",
  "sector-scoped business diligence",
  "ReportTemplate",
  "ReportWritingStyle",
]);
ensureExcludes("docs/architecture.md", removedSurfaceSnippets);

ensureIncludes("docs/agent-builder-quickstart.md", [
  "CDD-only",
  "sg://recipes",
  "sg://workflows",
  "sg://runtime",
  "blocked",
  "unsupported",
  "failed",
  "sg_business_dossier",
  "sg_boa_architecture_firms",
  "npm run verify",
]);
ensureExcludes("docs/agent-builder-quickstart.md", removedSurfaceSnippets);

ensureProductDocsUseOrchestratorPath([
  readmeTarget,
  "AGENTS.md",
  "docs/agent-builder-quickstart.md",
  "docs/product/corp-services-cdd.md",
  "docs/product/secondary-workflows.md",
  "examples/embeddable-widget/README.md",
  "examples/spreadsheet-addins/README.md",
]);

ensureIncludes("examples/README.md", [
  "business-dossier.md",
  "architecture-firm-diligence.md",
  "healthcare-supplier-diligence.md",
  "hotel-operator-lookup.md",
  "sector-scoped-business-diligence.md",
  "npm run diagnostics",
  "npm run test:smoke:profiles",
  "sg://runtime",
  "sg://playbooks",
  "sg://benchmarks",
  "sg_query completed, blocked, unsupported, and failed outcomes",
  "basic-client.py",
  "backend-worker-template.py",
  "queue-consumer-template.py",
]);
ensureExcludes("examples/README.md", removedSurfaceSnippets);

for (const path of ["smithery.yaml", "glama.json", "packages/mcp-server/package.json"]) {
  ensureIncludes(path, familyNames);
}

if (!Array.isArray(RUNTIME_CATALOG.queryStatusContract) || RUNTIME_CATALOG.queryStatusContract.length !== 5) {
  throw new Error("Built runtime catalog is missing the full sg_query status contract.");
}

for (const recipeName of [
  "Business Due Diligence",
  "Architecture Firm Diligence",
  "Healthcare Supplier Diligence",
  "Hotel Operator Lookup",
]) {
  if (!recipeNames.includes(recipeName)) {
    throw new Error(`Built recipe catalog is missing expected CDD recipe: ${recipeName}`);
  }
}

process.stdout.write(
  `Docs parity OK: ${totalTools} tools, ${familyCount} CDD catalog families, ${routedFamilyLabel}.\n`,
);
