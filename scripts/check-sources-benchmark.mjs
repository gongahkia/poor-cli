import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const artifactPath = resolve(root, process.argv[2] ?? "artifacts/sources/latest.json");
const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));

const REQUIRED_SOURCE_TOOLS = [
  "sg_nea_forecast_2hr",
  "sg_nea_air_quality",
  "sg_nea_rainfall",
  "sg_onemap_geocode",
  "sg_datagov_search",
  "sg_singstat_search",
  "sg_hawker_closures",
  "sg_nlb_libraries",
  "sg_sportsg_facilities",
  "sg_nparks_parks",
  "sg_pub_water_levels",
  "sg_pa_community_outlets",
  "sg_moe_schools",
  "sg_ecda_childcare_centres",
  "sg_msf_family_services",
  "sg_msf_student_care_services",
  "sg_msf_social_service_offices",
  "sg_moh_facilities",
];
const VALID_STATES = new Set(["ready", "stale", "gap", "credential_missing", "not_returned", "error"]);

const fail = (message) => {
  throw new Error(`${message} (${artifactPath})`);
};

if (artifact.schemaVersion !== "swee-source-live-benchmark/v1") {
  fail("Unexpected source benchmark schema version");
}

if (!Array.isArray(artifact.sourceChecks)) {
  fail("Source benchmark sourceChecks must be an array");
}

const checksByTool = new Map(artifact.sourceChecks.map((check) => [check.sourceTool, check]));
for (const sourceTool of REQUIRED_SOURCE_TOOLS) {
  const check = checksByTool.get(sourceTool);
  if (check === undefined) {
    fail(`Source benchmark is missing ${sourceTool}`);
  }
  if (!VALID_STATES.has(check.state)) {
    fail(`Source benchmark ${sourceTool} has invalid state ${check.state}`);
  }
  if (typeof check.family !== "string" || check.family.trim() === "") {
    fail(`Source benchmark ${sourceTool} is missing family`);
  }
  if (typeof check.coverage !== "string" || check.coverage.trim() === "") {
    fail(`Source benchmark ${sourceTool} is missing coverage text`);
  }
}

const AUTH_REQUIRED = new Set(["sg_onemap_geocode"]);
for (const sourceTool of REQUIRED_SOURCE_TOOLS) {
  const expected = AUTH_REQUIRED.has(sourceTool);
  if (checksByTool.get(sourceTool).authRequired !== expected) {
    fail(`${sourceTool} authRequired must be ${expected}`);
  }
}

if (artifact.pulseWeather?.auditId !== null && typeof artifact.pulseWeather?.auditId !== "string") {
  fail("Source benchmark pulseWeather.auditId must be string or null");
}

if (!Array.isArray(artifact.limits) || artifact.limits.length === 0) {
  fail("Source benchmark must include limits");
}

const serialized = JSON.stringify(artifact).toLowerCase();
for (const retiredTerm of ["company cdd", "business dossier", "counterparty"]) {
  if (serialized.includes(retiredTerm)) {
    fail(`Source benchmark must not include retired product term: ${retiredTerm}`);
  }
}

process.stdout.write(`source benchmark OK: ${artifact.sourceChecks.length} source checks.\n`);
