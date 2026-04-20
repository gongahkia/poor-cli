import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const { API_CATALOG, RECIPE_CATALOG, RUNTIME_CATALOG, TOOL_CATALOG, WORKFLOW_CATALOG } = await import(
  pathToFileURL(resolve(root, "packages/mcp-server/dist/tools/catalog.js")).href
);

const totalTools = TOOL_CATALOG.length;
const familyCount = API_CATALOG.length;
const directToolCount = API_CATALOG.reduce((sum, api) => sum + api.tools.length, 0);
const routedFamilyCount = API_CATALOG.filter((api) => api.preferredInterface === "sg_query").length;
const authFamilies = API_CATALOG.filter((api) => api.authRequired).map((api) => api.name);
const publicFamilies = API_CATALOG.filter((api) => !api.authRequired).map((api) => api.name);
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

ensureIncludes(readmeTarget, [
  `${totalTools} \`sg_*\` tools total`,
  `${familyCount} official data families`,
  `bounded preferred interface across ${routedFamilyCount} routed families`,
  "Business Registry Diligence",
  "sg_acra_entities",
  "sg://recipes",
  "sg://runtime",
  "sg://playbooks",
  "sg://benchmarks",
  "docs/product-audit.md",
  "docs/agent-builder-quickstart.md",
  "docs/market-conventions-audit.md",
  "docs/compatibility-matrix.md",
  "docs/known-issues.md",
  "docs/troubleshooting.md",
  "npm run diagnostics",
  "Route Planning",
  "SingStat Table Drilldown",
  "Dataset Collection Browse",
  "sg_civic_brief",
  "comparisons are supported only for two-planning-area prompts",
  "npm run test:smoke:public",
  ...familyNames,
]);
ensureExcludes(readmeTarget, [
  "CEA and BCA are direct-only in this tranche",
  "ACRA is the next business-diligence candidate",
]);

ensureIncludes("packages/skill/SKILL.md", [
  `${totalTools} \`sg_*\` tools total`,
  `${familyCount} official data families`,
  `bounded preferred interface across ${routedFamilyCount} routed families`,
  "Business Registry Diligence",
  "sg_acra_entities",
  "sg://recipes",
  "sg://runtime",
  "sg://playbooks",
  "sg://benchmarks",
  "Route Planning",
  "SingStat Table Drilldown",
  "Dataset Collection Browse",
  ...familyNames,
]);
ensureExcludes("packages/skill/SKILL.md", [
  "CEA and BCA are direct-only in this tranche",
  "CEA and BCA direct tools in this tranche",
]);

ensureIncludes("docs/architecture.md", [
  `${familyCount} official data families`,
  `bounded preferred interface across ${routedFamilyCount} routed families`,
  "business-registry workflows can route to ACRA, CEA, BCA, BOA, HSA, HLB, and GeBIZ",
  "sg://recipes",
  "sg://runtime",
  "sg://playbooks",
  "sg://benchmarks",
  "route planning can geocode postal codes before calling `sg_onemap_route`",
  "SingStat table drilldowns can move from browse to table to time-series reads",
  "data.gov collection browsing can continue into metadata, resources, and bounded rows",
  "only bounded two-planning-area comparisons are supported",
  "sg_civic_brief",
  ...familyNames,
]);
ensureExcludes("docs/architecture.md", [
  "ACRA remains deferred",
  "CEA and BCA remain direct-only in this tranche",
]);

ensureIncludes("docs/api-auth-guide.md", [
  `${authFamilies.length} authenticated upstreams`,
  ...authFamilies,
  ...publicFamilies,
  "HDB, CEA, BCA, BOA, HSA, HLB, and ACRA are intentionally covered through the shared data.gov.sg path or official file-download path",
]);

ensureIncludes("docs/contributing.md", [
  `${familyCount} data families`,
  "RegisteredToolDefinition[]",
  "tool-set.ts",
  "scripts/check-docs-parity.mjs",
  `${directToolCount} direct data tools`,
  "sg://recipes",
  "sg://playbooks",
  "sg://benchmarks",
  "RECIPE_CATALOG",
  "docs/agent-builder-quickstart.md",
]);

ensureIncludes("docs/product-audit.md", [
  "Actual value prop: yes, but narrow.",
  "sg://recipes",
  "Civic amenities and directories",
  "Education",
  "Healthcare facilities",
  "Procurement and tender discovery",
]);

ensureIncludes("docs/agent-builder-quickstart.md", [
  "sg://recipes",
  "sg://workflows",
  "sg://runtime",
  "sg://playbooks",
  "sg://benchmarks",
  "blocked",
  "unsupported",
  "failed",
  "sg_onemap_route",
  "sg_singstat_browse",
  "sg_datagov_browse",
  "npm run diagnostics",
  "docs/troubleshooting.md",
]);

ensureIncludes("examples/README.md", [
  "architecture-firm-diligence.md",
  "healthcare-supplier-diligence.md",
  "hotel-operator-lookup.md",
  "sector-scoped-business-diligence.md",
  "geospatial-routing.md",
  "npm run quick-start",
  "npm run test:smoke:live",
  "npm run test:smoke:public",
  "sg://runtime",
  "sg://playbooks",
  "sg://benchmarks",
  "failed outcomes",
  "sg_query completed, blocked, unsupported, and failed outcomes",
  "basic-client.py",
]);

ensureIncludes("docs/production-notes.md", [
  "sg://runtime",
  "sg://benchmarks",
  "npm run diagnostics",
]);

ensureIncludes("docs/compatibility-matrix.md", [
  "tier-1",
  "tier-2",
  "streamable HTTP",
  "test:smoke:remote",
  "test:smoke:container",
]);

ensureIncludes("docs/known-issues.md", [
  "KI-001",
  "OneMap auth",
  "ecosystem:snapshot",
  "Triage Rules",
]);

ensureIncludes("docs/contributing.md", [
  "npm run diagnostics",
  "do not silently drop source errors",
]);

ensureIncludes("examples/README.md", [
  "npm run diagnostics",
]);

if (existsSync(resolve(root, "CHANGELOG.md"))) {
  ensureIncludes("CHANGELOG.md", [
    `Tool count increased from 63 to ${totalTools}; API family count from 26 to ${familyCount}; routed families from 17 to ${routedFamilyCount}.`,
    "BOA, HSA, and HLB direct tool families",
    "Architecture Firm Diligence",
    "Healthcare Supplier Diligence",
    "Hotel Operator Lookup",
    "Sector Scoped Business Diligence",
  ]);
} else {
  process.stdout.write("CHANGELOG.md not found, skipping changelog parity checks.\n");
}

if (!Array.isArray(RUNTIME_CATALOG.queryStatusContract) || RUNTIME_CATALOG.queryStatusContract.length !== 5) {
  throw new Error("Built runtime catalog is missing the full sg_query status contract.");
}

for (const workflowName of workflowNames) {
  ensureIncludes(readmeTarget, [workflowName]);
  ensureIncludes("packages/skill/SKILL.md", [workflowName]);
}

for (const recipeName of ["Postal Route", "SingStat Drilldown", "HDB Rental Check"]) {
  if (!recipeNames.includes(recipeName)) {
    throw new Error(`Built recipe catalog is missing expected recipe: ${recipeName}`);
  }
}

for (const path of ["smithery.yaml", "glama.json", "packages/mcp-server/package.json"]) {
  ensureIncludes(path, familyNames);
}

process.stdout.write(
  `Docs parity OK: ${totalTools} tools, ${familyCount} families, ${authFamilies.length} authenticated families, ${routedFamilyCount} sg_query-routed families.\n`,
);
