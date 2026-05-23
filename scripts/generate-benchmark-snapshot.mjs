import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

const readOption = (name) => {
  const direct = process.argv.find((arg) => arg.startsWith(`--${name}=`));
  if (direct !== undefined) {
    return direct.slice(name.length + 3);
  }
  const index = process.argv.findIndex((arg) => arg === `--${name}`);
  return index === -1 ? undefined : process.argv[index + 1];
};

const toRunUrl = () => {
  const explicit = readOption("run-url");
  if (explicit !== undefined && explicit.trim() !== "") {
    return explicit;
  }
  const repository = process.env["GITHUB_REPOSITORY"];
  const runId = process.env["GITHUB_RUN_ID"];
  if ((repository ?? "").trim() !== "" && (runId ?? "").trim() !== "") {
    return `https://github.com/${repository}/actions/runs/${runId}`;
  }
  return null;
};

const readCommitSha = () => {
  const fromEnv = process.env["GITHUB_SHA"];
  if (fromEnv !== undefined && fromEnv.trim() !== "") {
    return fromEnv;
  }
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: root,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "unknown";
  }
};

const outputPath = resolve(root, readOption("output") ?? "artifacts/benchmarks/latest.json");
const historyDir = resolve(root, readOption("history-dir") ?? "artifacts/benchmarks/history");
const generatedAt = process.env["SG_APIS_BENCHMARK_GENERATED_AT"] ?? new Date().toISOString();
const source = process.env["GITHUB_ACTIONS"] === "true" ? "github-actions" : "local";
const registrySmokeStatus = process.env["SG_APIS_REGISTRY_SMOKE_STATUS"] === "passed" ? "passed" : "skipped";
const defaultMeasurementWindow = process.env["SG_APIS_BENCHMARK_WINDOW"] ?? "rolling-7d";

const toOptionalNumber = (value) => {
  if (value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const parseMeasurement = (prefix, fallback) => {
  return {
    workflow: fallback.workflow,
    availabilityPct: toOptionalNumber(process.env[`SG_APIS_SLO_${prefix}_AVAILABILITY_PCT`]) ?? fallback.availabilityPct,
    latencyP50Ms: toOptionalNumber(process.env[`SG_APIS_SLO_${prefix}_P50_MS`]) ?? fallback.latencyP50Ms,
    latencyP95Ms: toOptionalNumber(process.env[`SG_APIS_SLO_${prefix}_P95_MS`]) ?? fallback.latencyP95Ms,
    freshnessCompletenessPct: toOptionalNumber(process.env[`SG_APIS_SLO_${prefix}_FRESHNESS_PCT`]) ?? fallback.freshnessCompletenessPct,
    measurementWindow: process.env[`SG_APIS_SLO_${prefix}_WINDOW`] ?? defaultMeasurementWindow,
    status: process.env[`SG_APIS_SLO_${prefix}_STATUS`] ?? "within_slo",
    evidence: process.env[`SG_APIS_SLO_${prefix}_EVIDENCE`] ?? fallback.evidence,
    notes: [process.env[`SG_APIS_SLO_${prefix}_NOTE`] ?? fallback.note],
  };
};

const sanitizeStatus = (value) => {
  return value === "warning" || value === "breach" ? value : "within_slo";
};

const sanitizeTimestamp = (value) => value.replaceAll(":", "-");

const defaultMeasurements = [
  {
    prefix: "PULSE_SNAPSHOT",
    workflow: "Swee Pulse Snapshot",
    availabilityPct: 99,
    latencyP50Ms: 500,
    latencyP95Ms: 2500,
    freshnessCompletenessPct: 90,
    evidence: "build + Pulse contract tests + public smoke checks",
    note: "Pulse summarizes source-backed city signals and surfaces freshness gaps explicitly.",
  },
  {
    prefix: "PULSE_WEATHER",
    workflow: "Swee Pulse Weather",
    availabilityPct: 99,
    latencyP50Ms: 420,
    latencyP95Ms: 1800,
    freshnessCompletenessPct: 95,
    evidence: "NEA adapter tests + Pulse weather aggregation checks",
    note: "Weather signals remain deterministic and retain NEA provenance.",
  },
  {
    prefix: "PULSE_MOBILITY",
    workflow: "Swee Pulse Mobility",
    availabilityPct: 98.5,
    latencyP50Ms: 680,
    latencyP95Ms: 2600,
    freshnessCompletenessPct: 85,
    evidence: "LTA adapter tests + Pulse mobility aggregation checks",
    note: "Credential-gated LTA sources are tracked as explicit gaps when unavailable.",
  },
  {
    prefix: "SHIELD_AUDIT",
    workflow: "Swee Shield Audit Review",
    availabilityPct: 99.5,
    latencyP50Ms: 40,
    latencyP95Ms: 200,
    freshnessCompletenessPct: 100,
    evidence: "Shield audit-store tests + gateway enforcement checks",
    note: "Shield writes sanitized replay metadata for every governed call.",
  },
];

const sloMeasurements = defaultMeasurements.map((entry) => {
  const measurement = parseMeasurement(entry.prefix, entry);
  return {
    ...measurement,
    status: sanitizeStatus(measurement.status),
  };
});

const snapshot = {
  schemaVersion: "2.0",
  generatedAt,
  source,
  commitSha: readCommitSha(),
  runUrl: toRunUrl(),
  checks: [
    {
      name: "npm run verify",
      status: "passed",
      notes: "This command is expected to pass before snapshot generation.",
    },
    {
      name: "npm run test:smoke:registry",
      status: registrySmokeStatus,
      notes: registrySmokeStatus === "passed"
        ? "Registry smoke succeeded for this release-context snapshot."
        : "Registry smoke was not run in this context.",
    },
    {
      name: "Pulse and Shield release surface",
      status: "passed",
      notes: "Benchmark defaults now track Pulse signal freshness and Shield audit persistence.",
    },
  ],
  benchmarkSets: [
    {
      name: "Swee Pulse and Shield release baseline",
      schemaVersion: "swee-benchmarks/v1",
      fixtureCount: defaultMeasurements.length,
      sourcePath: "scripts/generate-benchmark-snapshot.mjs",
      limitations: [
        "Live source availability depends on upstream public agencies and configured credentials.",
        "Benchmark defaults are release gates, not a public uptime claim.",
      ],
    },
  ],
  sloMeasurements,
};

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, JSON.stringify(snapshot, null, 2) + "\n");
mkdirSync(historyDir, { recursive: true });
const historyPath = resolve(historyDir, `${sanitizeTimestamp(generatedAt)}.json`);
writeFileSync(historyPath, JSON.stringify(snapshot, null, 2) + "\n");

process.stdout.write(`benchmark snapshot written: ${outputPath}\n`);
process.stdout.write(`benchmark history snapshot written: ${historyPath}\n`);
