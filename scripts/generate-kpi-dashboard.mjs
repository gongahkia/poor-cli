#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { accessSync, constants, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const catalogDistPath = resolve(root, "packages/mcp-server/dist/tools/catalog.js");
const DEFAULT_THRESHOLDS_PATH = resolve(root, "config/kpi-thresholds.json");

const DEFAULT_THRESHOLD_POLICY = {
  schemaVersion: "kpi-thresholds/v1",
  installability: {
    requireVerifyPassed: true,
    allowedRegistrySmokeStatuses: ["passed", "skipped", "missing"],
    minInstallSuccessRatePct: null,
  },
  slo: {
    maxBreachCount: 0,
    maxWarningCount: 2,
  },
  docs: {
    maxDriftDefects: 2,
  },
  onboarding: {
    maxMeanTimeToFirstWorkflowMinutes: 120,
  },
  ecosystem: {
    minSingaporeMcpRepoCount: null,
    minStackoverflowQuestionCount: null,
  },
};

const parseArgs = (argv) => {
  const thresholdEnvPath = process.env["SG_APIS_KPI_THRESHOLDS_PATH"];
  const parsed = {
    benchmark: resolve(root, "artifacts/benchmarks/latest.json"),
    ecosystem: resolve(root, "artifacts/ecosystem/latest.json"),
    output: resolve(root, "artifacts/operations/latest.json"),
    historyDir: resolve(root, "artifacts/operations/history"),
    thresholds: thresholdEnvPath === undefined ? DEFAULT_THRESHOLDS_PATH : resolve(root, thresholdEnvPath),
    thresholdsExplicit: thresholdEnvPath !== undefined,
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === "--benchmark" && next !== undefined) {
      parsed.benchmark = resolve(root, next);
      index++;
      continue;
    }
    if (arg === "--ecosystem" && next !== undefined) {
      parsed.ecosystem = resolve(root, next);
      index++;
      continue;
    }
    if (arg === "--output" && next !== undefined) {
      parsed.output = resolve(root, next);
      index++;
      continue;
    }
    if (arg === "--history-dir" && next !== undefined) {
      parsed.historyDir = resolve(root, next);
      index++;
      continue;
    }
    if (arg === "--thresholds" && next !== undefined) {
      parsed.thresholds = resolve(root, next);
      parsed.thresholdsExplicit = true;
      index++;
      continue;
    }
  }

  return parsed;
};

const toOptionalNumber = (value) => {
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value === "string" && value.trim() === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const toOptionalInteger = (value) => {
  const parsed = toOptionalNumber(value);
  return parsed === null ? null : Math.trunc(parsed);
};

const safeReadJson = (filePath) => {
  if (!existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(readFileSync(filePath, "utf8"));
  } catch {
    return null;
  }
};

const toStringArray = (value, fallback) => {
  if (!Array.isArray(value)) {
    return fallback;
  }
  const normalized = value.filter((entry) => typeof entry === "string" && entry.trim() !== "").map((entry) => entry.trim());
  return normalized.length === 0 ? fallback : normalized;
};

const normalizeThresholdPolicy = (raw) => {
  const source = raw !== null && typeof raw === "object" ? raw : {};
  const installability = source.installability !== null && typeof source.installability === "object"
    ? source.installability
    : {};
  const slo = source.slo !== null && typeof source.slo === "object"
    ? source.slo
    : {};
  const docs = source.docs !== null && typeof source.docs === "object"
    ? source.docs
    : {};
  const onboarding = source.onboarding !== null && typeof source.onboarding === "object"
    ? source.onboarding
    : {};
  const ecosystem = source.ecosystem !== null && typeof source.ecosystem === "object"
    ? source.ecosystem
    : {};

  return {
    schemaVersion: "kpi-thresholds/v1",
    installability: {
      requireVerifyPassed: installability.requireVerifyPassed === undefined
        ? DEFAULT_THRESHOLD_POLICY.installability.requireVerifyPassed
        : Boolean(installability.requireVerifyPassed),
      allowedRegistrySmokeStatuses: toStringArray(
        installability.allowedRegistrySmokeStatuses,
        DEFAULT_THRESHOLD_POLICY.installability.allowedRegistrySmokeStatuses,
      ),
      minInstallSuccessRatePct: toOptionalNumber(installability.minInstallSuccessRatePct),
    },
    slo: {
      maxBreachCount: toOptionalInteger(slo.maxBreachCount) ?? DEFAULT_THRESHOLD_POLICY.slo.maxBreachCount,
      maxWarningCount: toOptionalInteger(slo.maxWarningCount) ?? DEFAULT_THRESHOLD_POLICY.slo.maxWarningCount,
    },
    docs: {
      maxDriftDefects: toOptionalInteger(docs.maxDriftDefects) ?? DEFAULT_THRESHOLD_POLICY.docs.maxDriftDefects,
    },
    onboarding: {
      maxMeanTimeToFirstWorkflowMinutes: toOptionalNumber(onboarding.maxMeanTimeToFirstWorkflowMinutes)
        ?? DEFAULT_THRESHOLD_POLICY.onboarding.maxMeanTimeToFirstWorkflowMinutes,
    },
    ecosystem: {
      minSingaporeMcpRepoCount: toOptionalInteger(ecosystem.minSingaporeMcpRepoCount),
      minStackoverflowQuestionCount: toOptionalInteger(ecosystem.minStackoverflowQuestionCount),
    },
  };
};

const resolveThresholdPolicy = (thresholdPath, explicitPath) => {
  if (!existsSync(thresholdPath)) {
    if (explicitPath) {
      throw new Error(`KPI threshold policy file not found: ${thresholdPath}`);
    }
    return {
      source: "default",
      sourcePath: null,
      policy: normalizeThresholdPolicy(DEFAULT_THRESHOLD_POLICY),
    };
  }

  const parsed = safeReadJson(thresholdPath);
  if (parsed === null) {
    throw new Error(`KPI threshold policy file is not valid JSON: ${thresholdPath}`);
  }

  return {
    source: "file",
    sourcePath: thresholdPath,
    policy: normalizeThresholdPolicy(parsed),
  };
};

const gitValue = (args) => {
  try {
    return execFileSync("git", args, {
      cwd: root,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "unknown";
  }
};

const toHistoryFilename = (isoTimestamp) => {
  return `${isoTimestamp.replace(/[:]/g, "").replace(/\.\d{3}Z$/, "Z")}.json`;
};

const summarizeSlo = (benchmarkSnapshot) => {
  const measurements = Array.isArray(benchmarkSnapshot?.sloMeasurements)
    ? benchmarkSnapshot.sloMeasurements
    : [];

  const statusCounts = { within_slo: 0, warning: 0, breach: 0, unknown: 0 };
  for (const entry of measurements) {
    const status = typeof entry?.status === "string" ? entry.status : "unknown";
    if (status === "within_slo" || status === "warning" || status === "breach") {
      statusCounts[status] += 1;
    } else {
      statusCounts.unknown += 1;
    }
  }

  const overallStatus = statusCounts.breach > 0
    ? "breach"
    : statusCounts.warning > 0
      ? "warning"
      : "within_slo";

  return {
    overallStatus,
    statusCounts,
    measurements,
  };
};

const summarizeInstallability = (benchmarkSnapshot) => {
  if (benchmarkSnapshot === null || typeof benchmarkSnapshot !== "object") {
    return {
      verifyPassed: null,
      registrySmokeStatus: "missing",
      installSuccessRatePct: toOptionalNumber(process.env["SG_APIS_KPI_INSTALL_SUCCESS_RATE_PCT"]),
      status: "unknown",
    };
  }

  const checks = Array.isArray(benchmarkSnapshot?.checks) ? benchmarkSnapshot.checks : [];
  const verifyCheck = checks.find((entry) => entry?.name === "npm run verify");
  const registrySmokeCheck = checks.find((entry) => entry?.name === "npm run test:smoke:registry");
  const verifyPassed = verifyCheck?.status === "passed";
  const registrySmokeStatus = typeof registrySmokeCheck?.status === "string"
    ? registrySmokeCheck.status
    : "missing";

  const envInstallRate = toOptionalNumber(process.env["SG_APIS_KPI_INSTALL_SUCCESS_RATE_PCT"]);
  return {
    verifyPassed,
    registrySmokeStatus,
    installSuccessRatePct: envInstallRate,
    status: verifyPassed ? "healthy" : "risk",
  };
};

const summarizeEcosystem = (ecosystemSnapshot) => {
  if (ecosystemSnapshot === null || typeof ecosystemSnapshot !== "object") {
    return {
      available: false,
      generatedAt: null,
      npmDownloadsLastMonth: [],
      singaporeMcpRepoCount: null,
      stackoverflowQuestionCount: null,
    };
  }

  const npmPackages = Array.isArray(ecosystemSnapshot.externalSignals?.npmPackages)
    ? ecosystemSnapshot.externalSignals.npmPackages
    : [];
  const npmDownloadsLastMonth = npmPackages.map((entry) => ({
    packageName: entry.packageName ?? "unknown",
    downloadsLastMonth: entry.downloadsLastMonth ?? null,
  }));

  return {
    available: true,
    generatedAt: typeof ecosystemSnapshot.generatedAt === "string" ? ecosystemSnapshot.generatedAt : null,
    npmDownloadsLastMonth,
    singaporeMcpRepoCount: ecosystemSnapshot.externalSignals?.singaporeMcpSearch?.totalCount ?? null,
    stackoverflowQuestionCount: ecosystemSnapshot.externalSignals?.stackoverflow?.tagInfo?.questionCount ?? null,
  };
};

const createAlert = (id, severity, metric, message, actual, threshold) => {
  return {
    id,
    severity,
    metric,
    message,
    actual,
    threshold,
  };
};

const statusRank = (severity) => {
  if (severity === "breach") return 2;
  if (severity === "warning") return 1;
  return 0;
};

const derivePolicyStatus = (alerts, metricPrefix) => {
  let best = "within_threshold";
  let bestRank = 0;

  for (const alert of alerts) {
    if (!alert.metric.startsWith(metricPrefix)) {
      continue;
    }
    const rank = statusRank(alert.severity);
    if (rank > bestRank) {
      best = alert.severity;
      bestRank = rank;
    }
  }

  return best;
};

const evaluatePolicy = (inputs, policy) => {
  const alerts = [];

  if (policy.installability.requireVerifyPassed) {
    if (inputs.installability.verifyPassed === false) {
      alerts.push(createAlert(
        "installability-verify",
        "breach",
        "installability.verifyPassed",
        "npm run verify did not pass in benchmark evidence.",
        inputs.installability.verifyPassed,
        true,
      ));
    } else if (inputs.installability.verifyPassed === null) {
      alerts.push(createAlert(
        "installability-verify-missing",
        "warning",
        "installability.verifyPassed",
        "Verify status is missing from benchmark evidence.",
        inputs.installability.verifyPassed,
        true,
      ));
    }
  }

  if (!policy.installability.allowedRegistrySmokeStatuses.includes(inputs.installability.registrySmokeStatus)) {
    alerts.push(createAlert(
      "installability-registry-smoke",
      "warning",
      "installability.registrySmokeStatus",
      "Registry smoke status is outside policy allow-list.",
      inputs.installability.registrySmokeStatus,
      policy.installability.allowedRegistrySmokeStatuses,
    ));
  }

  if (policy.installability.minInstallSuccessRatePct !== null) {
    if (inputs.installability.installSuccessRatePct === null) {
      alerts.push(createAlert(
        "installability-rate-missing",
        "warning",
        "installability.installSuccessRatePct",
        "Install success rate metric is missing.",
        null,
        policy.installability.minInstallSuccessRatePct,
      ));
    } else if (inputs.installability.installSuccessRatePct < policy.installability.minInstallSuccessRatePct) {
      alerts.push(createAlert(
        "installability-rate-low",
        "breach",
        "installability.installSuccessRatePct",
        "Install success rate is below policy threshold.",
        inputs.installability.installSuccessRatePct,
        policy.installability.minInstallSuccessRatePct,
      ));
    }
  }

  if (inputs.slo.statusCounts.breach > policy.slo.maxBreachCount) {
    alerts.push(createAlert(
      "slo-breach-count",
      "breach",
      "slo.breachCount",
      "SLO breach count exceeds policy threshold.",
      inputs.slo.statusCounts.breach,
      policy.slo.maxBreachCount,
    ));
  }

  if (inputs.slo.statusCounts.warning > policy.slo.maxWarningCount) {
    alerts.push(createAlert(
      "slo-warning-count",
      "warning",
      "slo.warningCount",
      "SLO warning count exceeds policy threshold.",
      inputs.slo.statusCounts.warning,
      policy.slo.maxWarningCount,
    ));
  }

  if (inputs.docsDriftDefects !== null && inputs.docsDriftDefects > policy.docs.maxDriftDefects) {
    alerts.push(createAlert(
      "docs-drift-defects",
      "warning",
      "docs.docsDriftDefects",
      "Documentation drift defects exceed policy threshold.",
      inputs.docsDriftDefects,
      policy.docs.maxDriftDefects,
    ));
  }

  if (
    inputs.meanTimeToFirstWorkflowMinutes !== null
    && inputs.meanTimeToFirstWorkflowMinutes > policy.onboarding.maxMeanTimeToFirstWorkflowMinutes
  ) {
    alerts.push(createAlert(
      "onboarding-ttfw",
      "warning",
      "onboarding.meanTimeToFirstWorkflowMinutes",
      "Mean time to first successful workflow exceeds policy threshold.",
      inputs.meanTimeToFirstWorkflowMinutes,
      policy.onboarding.maxMeanTimeToFirstWorkflowMinutes,
    ));
  }

  if (policy.ecosystem.minSingaporeMcpRepoCount !== null) {
    if (inputs.ecosystem.singaporeMcpRepoCount === null) {
      alerts.push(createAlert(
        "ecosystem-repo-count-missing",
        "warning",
        "ecosystem.singaporeMcpRepoCount",
        "Singapore MCP repository count is missing from ecosystem snapshot.",
        null,
        policy.ecosystem.minSingaporeMcpRepoCount,
      ));
    } else if (inputs.ecosystem.singaporeMcpRepoCount < policy.ecosystem.minSingaporeMcpRepoCount) {
      alerts.push(createAlert(
        "ecosystem-repo-count-low",
        "warning",
        "ecosystem.singaporeMcpRepoCount",
        "Singapore MCP repository count is below policy threshold.",
        inputs.ecosystem.singaporeMcpRepoCount,
        policy.ecosystem.minSingaporeMcpRepoCount,
      ));
    }
  }

  if (policy.ecosystem.minStackoverflowQuestionCount !== null) {
    if (inputs.ecosystem.stackoverflowQuestionCount === null) {
      alerts.push(createAlert(
        "ecosystem-stackoverflow-count-missing",
        "warning",
        "ecosystem.stackoverflowQuestionCount",
        "Stack Overflow MCP question count is missing from ecosystem snapshot.",
        null,
        policy.ecosystem.minStackoverflowQuestionCount,
      ));
    } else if (inputs.ecosystem.stackoverflowQuestionCount < policy.ecosystem.minStackoverflowQuestionCount) {
      alerts.push(createAlert(
        "ecosystem-stackoverflow-count-low",
        "warning",
        "ecosystem.stackoverflowQuestionCount",
        "Stack Overflow MCP question count is below policy threshold.",
        inputs.ecosystem.stackoverflowQuestionCount,
        policy.ecosystem.minStackoverflowQuestionCount,
      ));
    }
  }

  const overallPolicyStatus = derivePolicyStatus(alerts, "");

  return {
    alerts,
    overallPolicyStatus,
    componentStatus: {
      installability: derivePolicyStatus(alerts, "installability."),
      slo: derivePolicyStatus(alerts, "slo."),
      ecosystem: derivePolicyStatus(alerts, "ecosystem."),
      docs: derivePolicyStatus(alerts, "docs."),
      onboarding: derivePolicyStatus(alerts, "onboarding."),
    },
  };
};

const main = async () => {
  const args = parseArgs(process.argv.slice(2));

  try {
    accessSync(catalogDistPath, constants.R_OK);
  } catch {
    throw new Error("Missing built catalog. Run `npm run build` before generating the KPI dashboard.");
  }

  const {
    API_CATALOG,
    RECIPE_CATALOG,
    TOOL_CATALOG,
    WORKFLOW_CATALOG,
  } = await import(pathToFileURL(catalogDistPath).href);

  const benchmarkSnapshot = safeReadJson(args.benchmark);
  const ecosystemSnapshot = safeReadJson(args.ecosystem);
  const thresholdPolicy = resolveThresholdPolicy(args.thresholds, args.thresholdsExplicit);
  const generatedAt = new Date().toISOString();

  const installability = summarizeInstallability(benchmarkSnapshot);
  const slo = summarizeSlo(benchmarkSnapshot);
  const ecosystem = summarizeEcosystem(ecosystemSnapshot);
  const docsDriftDefects = toOptionalNumber(process.env["SG_APIS_KPI_DOCS_DRIFT_DEFECTS"]);
  const meanTimeToFirstWorkflowMinutes = toOptionalNumber(process.env["SG_APIS_KPI_TTFW_MINUTES"]);

  const policyEvaluation = evaluatePolicy(
    {
      installability,
      slo,
      ecosystem,
      docsDriftDefects,
      meanTimeToFirstWorkflowMinutes,
    },
    thresholdPolicy.policy,
  );

  const snapshot = {
    schemaVersion: "kpi-dashboard/v1",
    generatedAt,
    commitSha: gitValue(["rev-parse", "HEAD"]),
    commitShortSha: gitValue(["rev-parse", "--short", "HEAD"]),
    branch: gitValue(["branch", "--show-current"]),
    inputs: {
      benchmarkPath: args.benchmark,
      benchmarkFound: benchmarkSnapshot !== null,
      ecosystemPath: args.ecosystem,
      ecosystemFound: ecosystemSnapshot !== null,
    },
    policy: {
      source: thresholdPolicy.source,
      ...(thresholdPolicy.sourcePath === null ? {} : { sourcePath: thresholdPolicy.sourcePath }),
      thresholds: thresholdPolicy.policy,
    },
    localSurface: {
      tools: TOOL_CATALOG.length,
      apiFamilies: API_CATALOG.length,
      workflows: WORKFLOW_CATALOG.length,
      recipes: RECIPE_CATALOG.length,
      pulseFamilies: API_CATALOG.filter((entry) => entry.preferredInterface?.startsWith("swee_pulse_")).length,
    },
    kpis: {
      installability: {
        ...installability,
        policyStatus: policyEvaluation.componentStatus.installability,
      },
      slo: {
        ...slo,
        policyStatus: policyEvaluation.componentStatus.slo,
      },
      ecosystem: {
        ...ecosystem,
        policyStatus: policyEvaluation.componentStatus.ecosystem,
      },
      docsDriftDefects,
      docsPolicyStatus: policyEvaluation.componentStatus.docs,
      meanTimeToFirstWorkflowMinutes,
      onboardingPolicyStatus: policyEvaluation.componentStatus.onboarding,
    },
    alerts: policyEvaluation.alerts,
    overallPolicyStatus: policyEvaluation.overallPolicyStatus,
  };

  mkdirSync(dirname(args.output), { recursive: true });
  writeFileSync(args.output, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  mkdirSync(args.historyDir, { recursive: true });
  const historyPath = resolve(args.historyDir, toHistoryFilename(generatedAt));
  writeFileSync(historyPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");

  process.stdout.write(`kpi dashboard written: ${args.output}\n`);
  process.stdout.write(`kpi dashboard history written: ${historyPath}\n`);
  process.stdout.write(`${JSON.stringify({
    generatedAt,
    tools: snapshot.localSurface.tools,
    apiFamilies: snapshot.localSurface.apiFamilies,
    installabilityStatus: snapshot.kpis.installability.status,
    sloStatus: snapshot.kpis.slo.overallStatus,
    policyStatus: snapshot.overallPolicyStatus,
    alertCount: snapshot.alerts.length,
    ecosystemSnapshotAvailable: snapshot.kpis.ecosystem.available,
  }, null, 2)}\n`);
};

main().catch((error) => {
  process.stderr.write(`kpi dashboard generation failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
