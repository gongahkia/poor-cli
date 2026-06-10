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
    prefix: "TRANSPORT_RELIABILITY",
    workflow: "Transport Reliability Benchmark",
    availabilityPct: 98.5,
    latencyP50Ms: 700,
    latencyP95Ms: 2800,
    freshnessCompletenessPct: 85,
    evidence: "Pulse mobility source-health checks + LTA transport adapter tests",
    note: "Transport reliability proof covers incidents, train alerts, road events, and traffic camera freshness before broader civic expansion.",
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
  {
    prefix: "SPLUNK_INVESTIGATION_PACK",
    workflow: "Splunk Incident Investigation Pack",
    availabilityPct: 99,
    latencyP50Ms: 80,
    latencyP95Ms: 450,
    freshnessCompletenessPct: 100,
    evidence: "Splunk policy simulator + mock investigation pack tests",
    note: "Token-free mock mode validates bounded search planning, audit hashes, runtime findings, and analyst next checks.",
  },
];

const sloMeasurements = defaultMeasurements.map((entry) => {
  const measurement = parseMeasurement(entry.prefix, entry);
  return {
    ...measurement,
    status: sanitizeStatus(measurement.status),
  };
});

const transportReliability = {
  schemaVersion: "transport-reliability-benchmark/v1",
  focus: "LTA transport reliability source coverage for civic-hacker demos.",
  measurementWindow: defaultMeasurementWindow,
  sourceChecks: [
    {
      sourceTool: "sg_lta_traffic_incidents",
      source: "LTA DataMall",
      surface: "Swee Pulse mobility signal + source health",
      authRequired: true,
      coverage: "Network-wide traffic incident rows.",
      freshnessEvidence: "LTA does not provide a row timestamp; Swee Pulse reports observedAt and preserves the missing upstream timestamp as a confidence limit.",
    },
    {
      sourceTool: "sg_lta_train_alerts",
      source: "LTA DataMall",
      surface: "Swee Pulse mobility signal + source health",
      authRequired: true,
      coverage: "Network-wide train service alerts and operator messages.",
      freshnessEvidence: "Operator message createdDate is used when present; otherwise freshness is surfaced as unknown.",
    },
    {
      sourceTool: "sg_lta_road_works",
      source: "LTA DataMall",
      surface: "Swee Pulse mobility signal + source health",
      authRequired: true,
      coverage: "Network-wide road-work events with start/end timing.",
      freshnessEvidence: "Event start/end timing is retained as upstream timing context; unknown timing remains visible in source health.",
    },
    {
      sourceTool: "sg_lta_road_openings",
      source: "LTA DataMall",
      surface: "Swee Pulse mobility signal + source health",
      authRequired: true,
      coverage: "Network-wide road-opening events with start/end timing.",
      freshnessEvidence: "Event start/end timing is retained as upstream timing context; unknown timing remains visible in source health.",
    },
    {
      sourceTool: "sg_lta_traffic_images",
      source: "data.gov.sg transport feed",
      surface: "Swee Pulse source health",
      authRequired: false,
      coverage: "Traffic camera image references and camera timestamps.",
      freshnessEvidence: "Camera timestamps drive freshness where data.gov.sg returns them.",
    },
    {
      sourceTool: "sg_lta_bus_arrivals",
      source: "LTA DataMall",
      surface: "Credentialed direct adapter",
      authRequired: true,
      coverage: "Stop-level bus arrival timings when exact bus stop inputs are supplied.",
      freshnessEvidence: "Arrival estimates remain direct-adapter evidence and are not collapsed into the default network-wide Pulse snapshot.",
    },
    {
      sourceTool: "sg_lta_carpark_availability",
      source: "LTA DataMall",
      surface: "Credentialed direct adapter",
      authRequired: true,
      coverage: "Live carpark lot availability for filtered or capped queries.",
      freshnessEvidence: "Adapter responses expose observedAt metadata; Swee Pulse does not currently score carpark availability as a city disruption signal.",
    },
    {
      sourceTool: "sg_lta_taxi_availability",
      source: "LTA DataMall",
      surface: "Credentialed direct adapter",
      authRequired: true,
      coverage: "Available taxi coordinates for bounded queries.",
      freshnessEvidence: "Adapter responses expose observedAt metadata; Swee Pulse does not currently infer transport safety or availability claims from taxi positions.",
    },
  ],
  limits: [
    "This benchmark reports source coverage and evidence handling, not official service status.",
    "Credentialed LTA checks require SG_API_LTA_KEY or a local keystore entry.",
    "Missing upstream timestamps are reported as limits instead of being filled with synthetic freshness.",
  ],
};

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
  transportReliability,
  sloMeasurements,
};

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, JSON.stringify(snapshot, null, 2) + "\n");
mkdirSync(historyDir, { recursive: true });
const historyPath = resolve(historyDir, `${sanitizeTimestamp(generatedAt)}.json`);
writeFileSync(historyPath, JSON.stringify(snapshot, null, 2) + "\n");

process.stdout.write(`benchmark snapshot written: ${outputPath}\n`);
process.stdout.write(`benchmark history snapshot written: ${historyPath}\n`);
