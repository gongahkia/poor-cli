import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const catalog = await import(pathToFileURL(resolve(root, "packages/mcp-server/dist/tools/catalog.js")).href);

const benchmarkCatalog = catalog.BENCHMARK_CATALOG;
if (benchmarkCatalog?.schemaVersion !== "swee-benchmarks/v1") {
  throw new Error("BENCHMARK_CATALOG must use swee-benchmarks/v1.");
}

const workflows = new Set(benchmarkCatalog.workflows ?? []);
for (const workflow of ["Swee Pulse Snapshot", "Swee Pulse Mobility", "Transport Reliability Benchmark", "Swee Shield Audit Review"]) {
  if (!workflows.has(workflow)) {
    throw new Error(`BENCHMARK_CATALOG is missing workflow: ${workflow}`);
  }
}

const profiles = benchmarkCatalog.workflowProfiles ?? [];
if (!Array.isArray(profiles) || profiles.length < 4) {
  throw new Error("BENCHMARK_CATALOG must include Pulse, transport reliability, and Shield workflow profiles.");
}

for (const profile of profiles) {
  if (typeof profile.evidence !== "string" || profile.evidence.trim() === "") {
    throw new Error(`Benchmark profile ${profile.workflow ?? "<unknown>"} is missing evidence.`);
  }
  if (!Array.isArray(profile.notes) || profile.notes.length === 0) {
    throw new Error(`Benchmark profile ${profile.workflow ?? "<unknown>"} is missing notes.`);
  }
}

const transportSources = benchmarkCatalog.transportReliabilitySources ?? [];
if (!Array.isArray(transportSources) || transportSources.length < 5) {
  throw new Error("BENCHMARK_CATALOG must include transport reliability source profiles.");
}

for (const source of transportSources) {
  if (typeof source.sourceTool !== "string" || !source.sourceTool.startsWith("sg_lta_")) {
    throw new Error(`Transport reliability source is missing an LTA source tool: ${source.sourceTool ?? "<unknown>"}`);
  }
  if (typeof source.freshnessEvidence !== "string" || source.freshnessEvidence.trim() === "") {
    throw new Error(`Transport reliability source ${source.sourceTool} is missing freshness evidence.`);
  }
}

process.stdout.write(`Swee benchmark catalog OK: ${profiles.length} workflow profiles, ${transportSources.length} transport sources.\n`);
