#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { accessSync, constants, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const catalogDistPath = resolve(root, "packages/mcp-server/dist/tools/catalog.js");

const parseArgs = (argv) => {
  const parsed = {
    benchmark: resolve(root, "artifacts/benchmarks/latest.json"),
    ecosystem: resolve(root, "artifacts/ecosystem/latest.json"),
    output: resolve(root, "artifacts/operations/latest.json"),
    historyDir: resolve(root, "artifacts/operations/history"),
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
  }

  return parsed;
};

const toOptionalNumber = (value) => {
  if (value === undefined || value.trim() === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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
  const generatedAt = new Date().toISOString();

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
    localSurface: {
      tools: TOOL_CATALOG.length,
      apiFamilies: API_CATALOG.length,
      workflows: WORKFLOW_CATALOG.length,
      recipes: RECIPE_CATALOG.length,
      routedFamilies: API_CATALOG.filter((entry) => entry.preferredInterface === "sg_query").length,
    },
    kpis: {
      installability: summarizeInstallability(benchmarkSnapshot),
      slo: summarizeSlo(benchmarkSnapshot),
      ecosystem: summarizeEcosystem(ecosystemSnapshot),
      docsDriftDefects: toOptionalNumber(process.env["SG_APIS_KPI_DOCS_DRIFT_DEFECTS"]),
      meanTimeToFirstWorkflowMinutes: toOptionalNumber(process.env["SG_APIS_KPI_TTFW_MINUTES"]),
    },
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
    ecosystemSnapshotAvailable: snapshot.kpis.ecosystem.available,
  }, null, 2)}\n`);
};

main().catch((error) => {
  process.stderr.write(`kpi dashboard generation failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
