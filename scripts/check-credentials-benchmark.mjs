import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const artifactPath = resolve(root, process.argv[2] ?? "artifacts/credentials/latest.json");
const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));

const REQUIRED_TOOLS = ["sg_onemap_geocode", "sg_datagov_search"];
const VALID_STATES = new Set(["ready", "gap", "credential_missing", "error"]);

const fail = (message) => {
  throw new Error(`${message} (${artifactPath})`);
};

if (artifact.schemaVersion !== "swee-credential-live-benchmark/v1") {
  fail("Unexpected credential benchmark schema version");
}

if (!Array.isArray(artifact.credentialChecks)) {
  fail("Credential benchmark credentialChecks must be an array");
}

const checksByTool = new Map(artifact.credentialChecks.map((check) => [check.sourceTool, check]));
for (const toolName of REQUIRED_TOOLS) {
  const check = checksByTool.get(toolName);
  if (check === undefined) {
    fail(`Credential benchmark is missing ${toolName}`);
  }
  if (!VALID_STATES.has(check.state)) {
    fail(`${toolName} has invalid state ${check.state}`);
  }
  if (typeof check.authRequired !== "boolean") {
    fail(`${toolName} must include authRequired`);
  }
  if (!Array.isArray(check.credentialNames)) {
    fail(`${toolName} must include credentialNames`);
  }
}

if (checksByTool.get("sg_onemap_geocode").authRequired !== true) {
  fail("sg_onemap_geocode must be marked authRequired");
}

if (checksByTool.get("sg_datagov_search").authRequired !== false) {
  fail("sg_datagov_search must not be marked authRequired");
}

if (!Array.isArray(artifact.limits) || artifact.limits.length === 0) {
  fail("Credential benchmark must include limits");
}

const serialized = JSON.stringify(artifact).toLowerCase();
for (const retiredTerm of ["company cdd", "business dossier", "counterparty"]) {
  if (serialized.includes(retiredTerm)) {
    fail(`Credential benchmark must not include retired product term: ${retiredTerm}`);
  }
}

process.stdout.write(`credential benchmark OK: ${artifact.credentialChecks.length} credential checks.\n`);
