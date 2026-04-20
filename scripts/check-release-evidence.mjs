#!/usr/bin/env node

import { accessSync, constants, existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const catalogDistPath = resolve(root, "packages/mcp-server/dist/tools/catalog.js");

const parseArgs = (argv) => {
  const parsed = {
    benchmark: resolve(root, "artifacts/benchmarks/latest.json"),
    ecosystem: resolve(root, "artifacts/ecosystem/latest.json"),
    kpi: resolve(root, "artifacts/operations/latest.json"),
    maxAgeDays: 30,
    allowSloBreach: false,
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
    if (arg === "--kpi" && next !== undefined) {
      parsed.kpi = resolve(root, next);
      index++;
      continue;
    }
    if (arg === "--max-age-days" && next !== undefined) {
      const parsedDays = Number.parseInt(next, 10);
      if (Number.isFinite(parsedDays) && parsedDays > 0) {
        parsed.maxAgeDays = parsedDays;
      }
      index++;
      continue;
    }
    if (arg === "--allow-slo-breach") {
      parsed.allowSloBreach = true;
    }
  }

  return parsed;
};

const fail = (message) => {
  throw new Error(message);
};

const assert = (condition, message) => {
  if (!condition) {
    fail(message);
  }
};

const readJson = (filePath) => {
  assert(existsSync(filePath), `Missing release evidence file: ${filePath}`);
  try {
    return JSON.parse(readFileSync(filePath, "utf8"));
  } catch (error) {
    fail(`Invalid JSON in release evidence file ${filePath}: ${error instanceof Error ? error.message : String(error)}`);
  }
};

const parseTimestamp = (value, label) => {
  const parsed = Date.parse(value);
  assert(Number.isFinite(parsed), `${label} has invalid generatedAt timestamp: ${value}`);
  return parsed;
};

const assertFresh = (snapshot, label, maxAgeMs) => {
  assert(typeof snapshot.generatedAt === "string", `${label} snapshot missing generatedAt`);
  const generatedAtMs = parseTimestamp(snapshot.generatedAt, label);
  const ageMs = Date.now() - generatedAtMs;
  assert(ageMs <= maxAgeMs, `${label} snapshot is stale: ${snapshot.generatedAt}`);
};

const main = async () => {
  const args = parseArgs(process.argv.slice(2));
  const maxAgeMs = args.maxAgeDays * 24 * 60 * 60 * 1000;

  try {
    accessSync(catalogDistPath, constants.R_OK);
  } catch {
    fail("Missing built catalog. Run `npm run build` before checking release evidence.");
  }

  const {
    API_CATALOG,
    RECIPE_CATALOG,
    TOOL_CATALOG,
    WORKFLOW_CATALOG,
  } = await import(pathToFileURL(catalogDistPath).href);

  const benchmark = readJson(args.benchmark);
  const ecosystem = readJson(args.ecosystem);
  const kpi = readJson(args.kpi);

  assertFresh(benchmark, "benchmark", maxAgeMs);
  assertFresh(ecosystem, "ecosystem", maxAgeMs);
  assertFresh(kpi, "kpi", maxAgeMs);

  const benchmarkChecks = Array.isArray(benchmark.checks) ? benchmark.checks : [];
  const verifyCheck = benchmarkChecks.find((entry) => entry?.name === "npm run verify");
  assert(verifyCheck?.status === "passed", "Benchmark snapshot must include a passed npm run verify check.");
  assert(Array.isArray(benchmark.sloMeasurements) && benchmark.sloMeasurements.length > 0, "Benchmark snapshot is missing SLO measurements.");

  const hasBreach = benchmark.sloMeasurements.some((entry) => entry?.status === "breach");
  if (hasBreach && !args.allowSloBreach) {
    fail("Benchmark snapshot contains SLO breaches; fix forward or rerun with --allow-slo-breach for emergency release override.");
  }

  assert(kpi.schemaVersion === "kpi-dashboard/v1", "KPI dashboard schemaVersion mismatch.");
  assert(kpi.inputs?.benchmarkFound === true, "KPI dashboard was generated without benchmark evidence.");
  assert(kpi.inputs?.ecosystemFound === true, "KPI dashboard was generated without ecosystem evidence.");
  assert(kpi.localSurface?.tools === TOOL_CATALOG.length, "KPI localSurface.tools is out of sync with current catalog.");
  assert(kpi.localSurface?.apiFamilies === API_CATALOG.length, "KPI localSurface.apiFamilies is out of sync with current catalog.");
  assert(kpi.localSurface?.workflows === WORKFLOW_CATALOG.length, "KPI localSurface.workflows is out of sync with current catalog.");
  assert(kpi.localSurface?.recipes === RECIPE_CATALOG.length, "KPI localSurface.recipes is out of sync with current catalog.");

  assert(
    ecosystem.localSurface?.toolCount === TOOL_CATALOG.length,
    "Ecosystem snapshot localSurface.toolCount is out of sync with current catalog.",
  );
  assert(
    ecosystem.localSurface?.apiFamilyCount === API_CATALOG.length,
    "Ecosystem snapshot localSurface.apiFamilyCount is out of sync with current catalog.",
  );

  const summary = {
    benchmarkGeneratedAt: benchmark.generatedAt,
    ecosystemGeneratedAt: ecosystem.generatedAt,
    kpiGeneratedAt: kpi.generatedAt,
    tools: TOOL_CATALOG.length,
    apiFamilies: API_CATALOG.length,
    workflows: WORKFLOW_CATALOG.length,
    recipes: RECIPE_CATALOG.length,
    kpiInstallabilityStatus: kpi.kpis?.installability?.status ?? "unknown",
    kpiSloStatus: kpi.kpis?.slo?.overallStatus ?? "unknown",
  };

  process.stdout.write(`release evidence OK\n${JSON.stringify(summary, null, 2)}\n`);
};

main().catch((error) => {
  process.stderr.write(`release evidence check failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
