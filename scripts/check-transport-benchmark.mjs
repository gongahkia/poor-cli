import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const artifactPath = resolve(root, process.argv[2] ?? "artifacts/transport/latest.json");
const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));

const REQUIRED_SOURCE_TOOLS = [
  "sg_lta_traffic_incidents",
  "sg_lta_train_alerts",
  "sg_lta_road_works",
  "sg_lta_road_openings",
  "sg_lta_traffic_images",
];
const VALID_STATES = new Set(["ready", "stale", "gap", "credential_missing", "not_returned"]);

const fail = (message) => {
  throw new Error(`${message} (${artifactPath})`);
};

if (artifact.schemaVersion !== "swee-transport-live-benchmark/v1") {
  fail("Unexpected transport benchmark schema version");
}

if (!Array.isArray(artifact.sourceChecks)) {
  fail("Transport benchmark sourceChecks must be an array");
}

const checksByTool = new Map(artifact.sourceChecks.map((check) => [check.sourceTool, check]));
for (const sourceTool of REQUIRED_SOURCE_TOOLS) {
  const check = checksByTool.get(sourceTool);
  if (check === undefined) {
    fail(`Transport benchmark is missing ${sourceTool}`);
  }
  if (!VALID_STATES.has(check.state)) {
    fail(`Transport benchmark ${sourceTool} has invalid state ${check.state}`);
  }
  if (typeof check.coverage !== "string" || check.coverage.trim() === "") {
    fail(`Transport benchmark ${sourceTool} is missing coverage text`);
  }
}

const trafficImages = checksByTool.get("sg_lta_traffic_images");
if (trafficImages.authRequired !== false) {
  fail("sg_lta_traffic_images must remain marked no-auth in transport benchmark evidence");
}

for (const sourceTool of REQUIRED_SOURCE_TOOLS.filter((tool) => tool !== "sg_lta_traffic_images")) {
  if (checksByTool.get(sourceTool).authRequired !== true) {
    fail(`${sourceTool} must remain marked credentialed in transport benchmark evidence`);
  }
}

if (artifact.shield?.pulseAuditId !== null && typeof artifact.shield?.pulseAuditId !== "string") {
  fail("Transport benchmark shield.pulseAuditId must be string or null");
}

if (!Array.isArray(artifact.limits) || artifact.limits.length === 0) {
  fail("Transport benchmark must include limits");
}

const serialized = JSON.stringify(artifact).toLowerCase();
for (const retiredTerm of ["company cdd", "business dossier", "counterparty"]) {
  if (serialized.includes(retiredTerm)) {
    fail(`Transport benchmark must not include retired product term: ${retiredTerm}`);
  }
}

process.stdout.write(`transport benchmark OK: ${artifact.sourceChecks.length} source checks.\n`);
