import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const catalogPath = resolve(root, "packages/mcp-server/dist/tools/catalog.js");
const ownershipPath = resolve(root, "docs/ownership-matrix.json");

const requireFile = (filePath) => {
  if (!existsSync(filePath)) {
    throw new Error(`Missing required governance file: ${filePath}`);
  }
};

const ensureIncludes = (filePath, snippets) => {
  const text = readFileSync(filePath, "utf8");
  for (const snippet of snippets) {
    if (!text.includes(snippet)) {
      throw new Error(`${filePath} is missing required governance snippet: ${snippet}`);
    }
  }
};

const readJson = (filePath) => JSON.parse(readFileSync(filePath, "utf8"));

requireFile(catalogPath);
requireFile(ownershipPath);
requireFile(resolve(root, "docs/governance-checklist.md"));
requireFile(resolve(root, "docs/deprecation-policy.md"));
requireFile(resolve(root, "docs/quarterly-product-health-template.md"));
requireFile(resolve(root, "docs/release.md"));

const { API_CATALOG, WORKFLOW_CATALOG } = await import(pathToFileURL(catalogPath).href);
const matrix = readJson(ownershipPath);

if (!Array.isArray(matrix.apiFamilies) || !Array.isArray(matrix.workflows)) {
  throw new Error("docs/ownership-matrix.json must define apiFamilies[] and workflows[] arrays.");
}

const familiesByName = new Map(matrix.apiFamilies.map((entry) => [entry.name, entry]));
for (const family of API_CATALOG) {
  const owned = familiesByName.get(family.name);
  if (owned === undefined) {
    throw new Error(`Ownership matrix is missing API family owner: ${family.name}`);
  }
  if (typeof owned.primaryOwner !== "string" || owned.primaryOwner.trim() === "") {
    throw new Error(`API family ${family.name} is missing primaryOwner.`);
  }
  if (typeof owned.backupOwner !== "string" || owned.backupOwner.trim() === "") {
    throw new Error(`API family ${family.name} is missing backupOwner.`);
  }
}

const workflowsByName = new Map(matrix.workflows.map((entry) => [entry.name, entry]));
for (const workflow of WORKFLOW_CATALOG) {
  const owned = workflowsByName.get(workflow.name);
  if (owned === undefined) {
    throw new Error(`Ownership matrix is missing workflow owner: ${workflow.name}`);
  }
  if (typeof owned.primaryOwner !== "string" || owned.primaryOwner.trim() === "") {
    throw new Error(`Workflow ${workflow.name} is missing primaryOwner.`);
  }
  if (typeof owned.backupOwner !== "string" || owned.backupOwner.trim() === "") {
    throw new Error(`Workflow ${workflow.name} is missing backupOwner.`);
  }
}

ensureIncludes(resolve(root, "docs/governance-checklist.md"), [
  "No new API family without a documented use case, maintainer owner, and test plan.",
  "No release without passing verify, smoke, and policy checks.",
]);

ensureIncludes(resolve(root, "docs/deprecation-policy.md"), [
  "migration path",
  "Deprecation Notice",
  "Migration Mapping Template",
]);

ensureIncludes(resolve(root, "docs/quarterly-product-health-template.md"), [
  "KPI Summary",
  "Reliability And Security",
  "Adoption And Ecosystem",
  "Governance And Ownership",
]);

ensureIncludes(resolve(root, "docs/release.md"), [
  "Governance Checklist",
  "node ./scripts/check-governance.mjs",
]);

process.stdout.write(
  `Governance policy OK: ${API_CATALOG.length} API families and ${WORKFLOW_CATALOG.length} workflows have explicit owners.\n`,
);
