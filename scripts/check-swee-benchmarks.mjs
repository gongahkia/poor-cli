import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const catalog = await import(pathToFileURL(resolve(root, "packages/mcp-server/dist/tools/catalog.js")).href);

const benchmarkCatalog = catalog.BENCHMARK_CATALOG;
if (benchmarkCatalog?.schemaVersion !== "swee-benchmarks/v1") {
  throw new Error("BENCHMARK_CATALOG must use swee-benchmarks/v1.");
}

const workflows = new Set(benchmarkCatalog.workflows ?? []);
for (const workflow of ["Swee Pulse Snapshot", "Swee Shield Audit Review"]) {
  if (!workflows.has(workflow)) {
    throw new Error(`BENCHMARK_CATALOG is missing workflow: ${workflow}`);
  }
}

const profiles = benchmarkCatalog.workflowProfiles ?? [];
if (!Array.isArray(profiles) || profiles.length < 2) {
  throw new Error("BENCHMARK_CATALOG must include Pulse and Shield workflow profiles.");
}

for (const profile of profiles) {
  if (typeof profile.evidence !== "string" || profile.evidence.trim() === "") {
    throw new Error(`Benchmark profile ${profile.workflow ?? "<unknown>"} is missing evidence.`);
  }
  if (!Array.isArray(profile.notes) || profile.notes.length === 0) {
    throw new Error(`Benchmark profile ${profile.workflow ?? "<unknown>"} is missing notes.`);
  }
}

process.stdout.write(`Swee benchmark catalog OK: ${profiles.length} workflow profiles.\n`);
