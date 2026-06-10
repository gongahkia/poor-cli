import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const benchmarkPath = resolve(root, "artifacts/benchmarks/latest.json");
const statusPath = resolve(root, "artifacts/status/public-status.json");
const markdownPath = resolve(root, "docs/status/public-status.md");

const benchmark = JSON.parse(readFileSync(benchmarkPath, "utf8"));
const measurements = Array.isArray(benchmark.sloMeasurements) ? benchmark.sloMeasurements : [];
const benchmarkSets = Array.isArray(benchmark.benchmarkSets) ? benchmark.benchmarkSets : [];
const checks = Array.isArray(benchmark.checks) ? benchmark.checks : [];
const transportReliability = benchmark.transportReliability && typeof benchmark.transportReliability === "object"
  ? benchmark.transportReliability
  : null;

const availabilityValues = measurements
  .map((item) => Number(item.availabilityPct))
  .filter((value) => Number.isFinite(value));
const freshnessValues = measurements
  .map((item) => Number(item.freshnessCompletenessPct))
  .filter((value) => Number.isFinite(value));

const average = (values) =>
  values.length === 0
    ? null
    : Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100) / 100;

const failures = [
  ...checks
    .filter((check) => check.status !== "passed" && check.status !== "skipped")
    .map((check) => ({
      scope: "check",
      name: check.name,
      status: check.status,
      notes: check.notes,
    })),
  ...measurements
    .filter((item) => item.status !== "within_slo")
    .map((item) => ({
      scope: "workflow",
      name: item.workflow,
      status: item.status,
      notes: Array.isArray(item.notes) ? item.notes.join(" ") : "",
    })),
];

const status = {
  schemaVersion: "swee-public-status/v1",
  generatedAt: benchmark.generatedAt,
  source: benchmark.source,
  commitSha: benchmark.commitSha,
  runUrl: benchmark.runUrl,
  benchmarkSnapshot: {
    path: "artifacts/benchmarks/latest.json",
    schemaVersion: benchmark.schemaVersion,
    checks,
    benchmarkSets,
  },
  transportReliability,
  uptime: {
    measurementWindow: measurements[0]?.measurementWindow ?? "unknown",
    averageAvailabilityPct: average(availabilityValues),
    workflows: measurements.map((item) => ({
      workflow: item.workflow,
      availabilityPct: item.availabilityPct,
      latencyP50Ms: item.latencyP50Ms,
      latencyP95Ms: item.latencyP95Ms,
      status: item.status,
      evidence: item.evidence,
    })),
  },
  freshness: {
    averageCompletenessPct: average(freshnessValues),
    workflows: measurements.map((item) => ({
      workflow: item.workflow,
      freshnessCompletenessPct: item.freshnessCompletenessPct,
      measurementWindow: item.measurementWindow,
      notes: item.notes,
    })),
  },
  failures,
  limits: [
    "This page is generated from local or CI benchmark evidence; it is not an SLA.",
    "Skipped smoke checks are reported separately and do not count as failures.",
    "Freshness completeness measures whether outputs expose freshness metadata, not whether upstream data is intrinsically complete.",
  ],
};

const fmt = (value, suffix = "") => value === null || value === undefined ? "n/a" : `${value}${suffix}`;
const md = [
  "# Public Benchmark And Source Status",
  "",
  `Generated: ${status.generatedAt}`,
  "",
  `Source: ${status.source}`,
  "",
  `Commit: ${status.commitSha}`,
  "",
  "## Release Evidence",
  "",
  `Measurement window: ${status.uptime.measurementWindow}`,
  "",
  `Average availability-style gate: ${fmt(status.uptime.averageAvailabilityPct, "%")}`,
  "",
  "| Workflow | Availability-style gate | p50 | p95 | Status |",
  "| --- | ---: | ---: | ---: | --- |",
  ...status.uptime.workflows.map((item) =>
    `| ${item.workflow} | ${fmt(item.availabilityPct, "%")} | ${fmt(item.latencyP50Ms, " ms")} | ${fmt(item.latencyP95Ms, " ms")} | ${item.status} |`,
  ),
  "",
  "## Freshness",
  "",
  `Average freshness metadata completeness: ${fmt(status.freshness.averageCompletenessPct, "%")}`,
  "",
  "| Workflow | Freshness completeness | Window | Notes |",
  "| --- | ---: | --- | --- |",
  ...status.freshness.workflows.map((item) =>
    `| ${item.workflow} | ${fmt(item.freshnessCompletenessPct, "%")} | ${item.measurementWindow} | ${(item.notes ?? []).join(" ")} |`,
  ),
  "",
  "## Failures",
  "",
  status.failures.length === 0
    ? "No warning or breach statuses in the latest snapshot."
    : status.failures.map((item) => `- ${item.scope}/${item.name}: ${item.status} - ${item.notes}`).join("\n"),
  "",
  transportReliability === null ? "" : [
    "## Transport Reliability",
    "",
    `${transportReliability.focus ?? "LTA transport reliability source coverage."}`,
    "",
    "| Source tool | Surface | Auth | Coverage | Freshness evidence |",
    "| --- | --- | --- | --- | --- |",
    ...((transportReliability.sourceChecks ?? []).map((item) =>
      `| ${item.sourceTool} | ${item.surface} | ${item.authRequired ? "required" : "not required"} | ${item.coverage} | ${item.freshnessEvidence} |`,
    )),
    "",
    ...((transportReliability.limits ?? []).map((item) => `- ${item}`)),
    "",
  ].join("\n"),
  "## Benchmarks",
  "",
  "| Set | Fixtures | Schema | Source |",
  "| --- | ---: | --- | --- |",
  ...status.benchmarkSnapshot.benchmarkSets.map((item) =>
    `| ${item.name} | ${item.fixtureCount ?? "n/a"} | ${item.schemaVersion ?? "n/a"} | ${item.sourcePath ?? "n/a"} |`,
  ),
  "",
  "## Limits",
  "",
  ...status.limits.map((item) => `- ${item}`),
  "",
].join("\n");

mkdirSync(dirname(statusPath), { recursive: true });
mkdirSync(dirname(markdownPath), { recursive: true });
writeFileSync(statusPath, JSON.stringify(status, null, 2) + "\n");
writeFileSync(markdownPath, md);

process.stdout.write(`public status written: ${statusPath}\n`);
process.stdout.write(`public status markdown written: ${markdownPath}\n`);
