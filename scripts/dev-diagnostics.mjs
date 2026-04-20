#!/usr/bin/env node

import { accessSync, constants } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const catalogDistPath = resolve(root, "packages/mcp-server/dist/tools/catalog.js");

const fail = (message) => {
  process.stderr.write(`diagnostics failed: ${message}\n`);
  process.exit(1);
};

const assert = (condition, message) => {
  if (!condition) {
    fail(message);
  }
};

try {
  accessSync(catalogDistPath, constants.R_OK);
} catch {
  fail("missing built catalog. run `npm run build` first.");
}

const {
  API_CATALOG,
  RECIPE_CATALOG,
  RESOURCE_URIS,
  RUNTIME_CATALOG,
  TOOL_CATALOG,
  WORKFLOW_CATALOG,
} = await import(pathToFileURL(catalogDistPath).href);

assert(Array.isArray(TOOL_CATALOG) && TOOL_CATALOG.length > 0, "TOOL_CATALOG is empty.");
assert(Array.isArray(API_CATALOG) && API_CATALOG.length > 0, "API_CATALOG is empty.");
assert(Array.isArray(WORKFLOW_CATALOG) && WORKFLOW_CATALOG.length > 0, "WORKFLOW_CATALOG is empty.");
assert(Array.isArray(RECIPE_CATALOG) && RECIPE_CATALOG.length > 0, "RECIPE_CATALOG is empty.");

const toolNames = TOOL_CATALOG.map((tool) => tool.name);
const uniqueToolNames = new Set(toolNames);
assert(uniqueToolNames.size === toolNames.length, "duplicate tool names detected in TOOL_CATALOG.");

const sgQuery = TOOL_CATALOG.find((tool) => tool.name === "sg_query");
assert(sgQuery !== undefined, "sg_query missing from TOOL_CATALOG.");
assert(sgQuery.preferred === true, "sg_query must remain marked as preferred.");

for (const api of API_CATALOG) {
  for (const toolName of api.tools) {
    assert(uniqueToolNames.has(toolName), `API catalog references unknown tool: ${toolName}`);
  }
}

for (const workflow of WORKFLOW_CATALOG) {
  for (const entrypoint of workflow.entrypoints) {
    assert(uniqueToolNames.has(entrypoint.tool), `workflow ${workflow.name} references unknown tool ${entrypoint.tool}`);
  }
}

for (const recipe of RECIPE_CATALOG) {
  assert(
    uniqueToolNames.has(recipe.preferredEntrypoint.tool),
    `recipe ${recipe.name} references unknown preferred tool ${recipe.preferredEntrypoint.tool}`,
  );
  for (const fallbackTool of recipe.fallbackTools) {
    assert(uniqueToolNames.has(fallbackTool), `recipe ${recipe.name} references unknown fallback tool ${fallbackTool}`);
  }
}

const requiredResourceKeys = [
  "apis",
  "opsTaxonomy",
  "tools",
  "workflows",
  "recipes",
  "runtime",
  "playbooks",
  "benchmarks",
];
for (const key of requiredResourceKeys) {
  const uri = RESOURCE_URIS[key];
  assert(typeof uri === "string" && uri.startsWith("sg://"), `RESOURCE_URIS.${key} must be an sg:// URI.`);
}

assert(Array.isArray(RUNTIME_CATALOG.toolsetProfiles), "RUNTIME_CATALOG.toolsetProfiles must be an array.");
assert(RUNTIME_CATALOG.toolsetProfiles.length >= 4, "RUNTIME_CATALOG.toolsetProfiles must expose all profile presets.");
for (const profile of RUNTIME_CATALOG.toolsetProfiles) {
  assert(typeof profile.profile === "string" && profile.profile.length > 0, "toolset profile must include profile name.");
  assert(typeof profile.intent === "string" && profile.intent.length > 0, `toolset profile ${profile.profile} must include intent.`);
  assert(Array.isArray(profile.toolsets) && profile.toolsets.length > 0, `toolset profile ${profile.profile} must include toolsets.`);
}

const summary = {
  tools: TOOL_CATALOG.length,
  apis: API_CATALOG.length,
  workflows: WORKFLOW_CATALOG.length,
  recipes: RECIPE_CATALOG.length,
  resources: requiredResourceKeys.length,
};

process.stdout.write("diagnostics ok\n");
process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
