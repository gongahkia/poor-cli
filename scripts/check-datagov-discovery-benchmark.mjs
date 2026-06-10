import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const artifactPath = resolve(root, process.argv[2] ?? "artifacts/datagov-discovery/latest.json");
const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));

const REQUIRED_QUERIES = ["weather", "hawker", "school", "clinic", "park", "water", "community", "transport"];
const VALID_STATES = new Set(["ready", "gap", "error"]);

const fail = (message) => {
  throw new Error(`${message} (${artifactPath})`);
};

if (artifact.schemaVersion !== "swee-datagov-discovery-live-benchmark/v1") {
  fail("Unexpected data.gov discovery benchmark schema version");
}

if (!Array.isArray(artifact.queries)) {
  fail("data.gov discovery benchmark queries must be an array");
}

const queriesByName = new Map(artifact.queries.map((query) => [query.query, query]));
for (const queryName of REQUIRED_QUERIES) {
  const query = queriesByName.get(queryName);
  if (query === undefined) {
    fail(`data.gov discovery benchmark is missing ${queryName}`);
  }
  if (!VALID_STATES.has(query.state)) {
    fail(`${queryName} has invalid state ${query.state}`);
  }
  if (!Number.isInteger(query.resultCount) || query.resultCount < 0) {
    fail(`${queryName} has invalid resultCount`);
  }
  if (!Array.isArray(query.topDatasets)) {
    fail(`${queryName} topDatasets must be an array`);
  }
  for (const dataset of query.topDatasets) {
    if (typeof dataset.datasetId !== "string" || dataset.datasetId.trim() === "") {
      fail(`${queryName} contains a dataset without datasetId`);
    }
    if (typeof dataset.supportedFormat !== "boolean") {
      fail(`${queryName} dataset ${dataset.datasetId} must include supportedFormat`);
    }
  }
}

if (!Array.isArray(artifact.limits) || artifact.limits.length === 0) {
  fail("data.gov discovery benchmark must include limits");
}

const serialized = JSON.stringify(artifact).toLowerCase();
for (const retiredTerm of ["company cdd", "business dossier", "counterparty"]) {
  if (serialized.includes(retiredTerm)) {
    fail(`data.gov discovery benchmark must not include retired product term: ${retiredTerm}`);
  }
}

process.stdout.write(`data.gov discovery benchmark OK: ${artifact.queries.length} query checks.\n`);
