import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const artifactPath = resolve(root, process.argv[2] ?? "artifacts/sources/contracts-latest.json");
const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));

const REQUIRED_DATASETS = [
  "d_bda4baa634dd1cc7a6c7cad5f19e2d68",
  "d_27b8dae65d9ca1539e14d09578b17cbf",
  "d_9b87bab59d036a60fad2a91530e10773",
  "d_77d7ec97be83d44f61b85454f844382f",
  "d_31333fa5cf0834f012d840365b336610",
  "d_9de02d3fb33d96da1855f4fbef549a0f",
  "d_688b934f82c1059ed0a6993d2a829089",
  "d_5d668e3f544335f8028f546827b773b4",
  "d_696c994c50745b079b3684f0e90ffc53",
  "d_add23c06f7267e799185c79ccaa2099b",
  "d_77e6e0d58ce4743dab1f26dfcbbeb6f4",
  "d_22cfe2aed0bf20a679ab59bcaf0f8248",
  "d_548c33ea2d99e29ec63a7cc9edcccedc",
];
const VALID_STATES = new Set(["ready", "gap", "error"]);
const VALID_READERS = new Set(["datastore", "geojson", "csv", "xlsx"]);

const fail = (message) => {
  throw new Error(`${message} (${artifactPath})`);
};

if (artifact.schemaVersion !== "swee-source-contracts-live-benchmark/v1") {
  fail("Unexpected source-contract benchmark schema version");
}

if (!Array.isArray(artifact.contractChecks)) {
  fail("Source-contract benchmark contractChecks must be an array");
}

const checksByDataset = new Map(artifact.contractChecks.map((check) => [check.datasetId, check]));
for (const datasetId of REQUIRED_DATASETS) {
  const check = checksByDataset.get(datasetId);
  if (check === undefined) {
    fail(`Source-contract benchmark is missing ${datasetId}`);
  }
  if (!VALID_STATES.has(check.state)) {
    fail(`${datasetId} has invalid state ${check.state}`);
  }
  if (!VALID_READERS.has(check.reader)) {
    fail(`${datasetId} has invalid reader ${check.reader}`);
  }
  if (!Array.isArray(check.expectedFields) || check.expectedFields.length === 0) {
    fail(`${datasetId} must declare expectedFields`);
  }
  if (!Array.isArray(check.missingFields) || !Array.isArray(check.observedFields)) {
    fail(`${datasetId} must include missingFields and observedFields`);
  }
  if (check.state === "ready" && (check.recordCount < 1 || check.missingFields.length !== 0)) {
    fail(`${datasetId} ready state requires records and no missing fields`);
  }
}

if (!Array.isArray(artifact.limits) || artifact.limits.length === 0) {
  fail("Source-contract benchmark must include limits");
}

const serialized = JSON.stringify(artifact).toLowerCase();
for (const retiredTerm of ["company cdd", "business dossier", "counterparty"]) {
  if (serialized.includes(retiredTerm)) {
    fail(`Source-contract benchmark must not include retired product term: ${retiredTerm}`);
  }
}

process.stdout.write(`source contracts benchmark OK: ${artifact.contractChecks.length} contract checks.\n`);
