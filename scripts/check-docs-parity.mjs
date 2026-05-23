import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const { API_CATALOG, RECIPE_CATALOG, RUNTIME_CATALOG, TOOL_CATALOG, WORKFLOW_CATALOG } = await import(
  pathToFileURL(resolve(root, "packages/mcp-server/dist/tools/catalog.js")).href
);

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

const toolNames = new Set(TOOL_CATALOG.map((tool) => tool.name));
const recipeNames = new Set(RECIPE_CATALOG.map((recipe) => recipe.name));
const workflowNames = new Set(WORKFLOW_CATALOG.map((workflow) => workflow.name));
const apiNames = new Set(API_CATALOG.map((api) => api.name));

for (const toolName of [
  "swee_pulse_snapshot",
  "swee_pulse_mobility",
  "swee_pulse_weather",
  "swee_pulse_explain",
  "swee_shield_audit_lookup",
  "swee_shield_scan_tools",
]) {
  if (!toolNames.has(toolName)) {
    throw new Error(`Built tool catalog is missing ${toolName}.`);
  }
}

for (const familyName of ["Swee Pulse", "Swee Shield", "Operations"]) {
  if (!apiNames.has(familyName)) {
    throw new Error(`Built API catalog is missing ${familyName}.`);
  }
}

for (const workflowName of ["Swee Pulse Snapshot", "Swee Shield Audit Review"]) {
  if (!workflowNames.has(workflowName)) {
    throw new Error(`Built workflow catalog is missing ${workflowName}.`);
  }
}

for (const recipeName of ["Pulse Overview", "Recent Shield Audit"]) {
  if (!recipeNames.has(recipeName)) {
    throw new Error(`Built recipe catalog is missing ${recipeName}.`);
  }
}

if (RUNTIME_CATALOG.schemaVersion !== "swee-runtime/v1") {
  throw new Error("Built runtime catalog must use swee-runtime/v1.");
}

const staleProductSnippets = [
  "Dude CDD",
  "CDD-only",
  "CDD orchestrator",
  "Search a Singapore company or UEN. Get a cited CDD report",
  "/api/v1/dude",
  "Report Builder",
  "Company/UEN CDD report",
];

ensureIncludes(readmeTarget, [
  "Swee SG",
  "Swee Shield",
  "Swee Pulse",
  "swee_pulse_snapshot",
  "swee_shield_audit_lookup",
  "/api/v1/pulse/snapshot",
  "SWEE_WEB_ORIGIN_ALLOWLIST",
  "npm run test:smoke:profiles",
]);
ensureExcludes(readmeTarget, staleProductSnippets);

ensureIncludes("AGENTS.md", [
  "Swee SG",
  "Swee Pulse",
  "Swee Shield",
  "Never invent public-data values",
  "swee_pulse_snapshot",
  "swee_shield_audit_lookup",
]);
ensureExcludes("AGENTS.md", staleProductSnippets);

ensureIncludes("docs/architecture.md", [
  "Swee Pulse",
  "Swee Shield",
  "Pulse Contract",
  "Shield Contract",
  "/api/v1/pulse/snapshot",
]);
ensureExcludes("docs/architecture.md", staleProductSnippets);

ensureIncludes("docs/deployment.md", [
  "Swee SG",
  "swee-gateway",
  "swee-mcp",
  "SWEE_WEB_ORIGIN_ALLOWLIST",
  "ghcr.io/gongahkia/swee-sg",
]);

ensureIncludes("docs/naming-and-remotes.md", [
  "Swee SG",
  "swee-sg",
  "swee-shield",
  "ghcr.io/gongahkia/swee-sg",
  "SWEE_WEB_ORIGIN_ALLOWLIST",
]);

ensureIncludes("examples/README.md", [
  "browser-extension/",
  "spreadsheet-addins/",
  "embeddable-widget/",
  "/api/v1/pulse/snapshot",
  "npm run widget:check",
]);
ensureExcludes("examples/README.md", staleProductSnippets);

ensureIncludes("examples/browser-extension/README.md", [
  "Swee Pulse",
  "/api/v1/pulse/snapshot",
  "area",
]);
ensureIncludes("examples/spreadsheet-addins/README.md", [
  "SWEE_PULSE_SNAPSHOT",
  "SWEE_PULSE_SIGNALS",
  "SWEE_PULSE_SOURCES",
]);
ensureIncludes("examples/embeddable-widget/README.md", [
  "swee-pulse-widget",
  "/api/v1/pulse/snapshot",
  "swee-pulse-complete",
]);

ensureIncludes("packages/mcp-server/README.md", [
  "@swee-sg/shield",
  "swee-sg",
  "swee_pulse_snapshot",
  "swee_shield_scan_tools",
]);
ensureExcludes("packages/mcp-server/README.md", staleProductSnippets);

process.stdout.write(
  `Docs parity OK: ${TOOL_CATALOG.length} tools, ${API_CATALOG.length} API families, ${WORKFLOW_CATALOG.length} workflows.\n`,
);
