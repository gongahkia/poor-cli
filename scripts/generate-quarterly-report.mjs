#!/usr/bin/env node

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

const parseArgs = (argv) => {
  const parsed = {
    benchmark: resolve(root, "artifacts/benchmarks/latest.json"),
    ecosystem: resolve(root, "artifacts/ecosystem/latest.json"),
    kpi: resolve(root, "artifacts/operations/latest.json"),
    quarter: null,
    output: null,
    owner: process.env["SG_APIS_QUARTERLY_OWNER"] ?? "maintainer",
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
    if (arg === "--quarter" && next !== undefined) {
      parsed.quarter = next.trim();
      index++;
      continue;
    }
    if (arg === "--output" && next !== undefined) {
      parsed.output = resolve(root, next);
      index++;
      continue;
    }
    if (arg === "--owner" && next !== undefined) {
      parsed.owner = next.trim() === "" ? parsed.owner : next.trim();
      index++;
      continue;
    }
  }

  return parsed;
};

const readRequiredJson = (filePath, label) => {
  if (!existsSync(filePath)) {
    throw new Error(`Missing ${label} artifact: ${filePath}`);
  }
  try {
    return JSON.parse(readFileSync(filePath, "utf8"));
  } catch (error) {
    throw new Error(`Invalid JSON for ${label} artifact ${filePath}: ${error instanceof Error ? error.message : String(error)}`);
  }
};

const toQuarter = (date) => {
  const month = date.getUTCMonth() + 1;
  const quarter = Math.floor((month - 1) / 3) + 1;
  return `${date.getUTCFullYear()}-Q${quarter}`;
};

const toPct = (value) => {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "n/a";
};

const toNumber = (value) => {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "n/a";
};

const summarizeWorkflowCompletion = (benchmark) => {
  const measurements = Array.isArray(benchmark?.sloMeasurements) ? benchmark.sloMeasurements : [];
  if (measurements.length === 0) {
    return { target: ">= 90%", actual: "n/a", status: "risk", notes: "No SLO workflow measurements found." };
  }
  const averageAvailability = measurements.reduce((sum, entry) => sum + (Number(entry?.availabilityPct) || 0), 0) / measurements.length;
  const status = averageAvailability >= 90 ? "on track" : "risk";
  return {
    target: ">= 90%",
    actual: `${averageAvailability.toFixed(1)}%`,
    status,
    notes: `Average availability across ${measurements.length} tracked workflows.`,
  };
};

const summarizeSloCompliance = (benchmark) => {
  const measurements = Array.isArray(benchmark?.sloMeasurements) ? benchmark.sloMeasurements : [];
  const counts = { within_slo: 0, warning: 0, breach: 0 };
  for (const entry of measurements) {
    if (entry?.status === "breach") counts.breach += 1;
    else if (entry?.status === "warning") counts.warning += 1;
    else counts.within_slo += 1;
  }
  const status = counts.breach > 0 ? "risk" : counts.warning > 0 ? "watch" : "on track";
  return {
    target: "0 breaches",
    actual: `${counts.within_slo} within / ${counts.warning} warning / ${counts.breach} breach`,
    status,
    notes: `${measurements.length} workflow SLO measurements in benchmark snapshot.`,
  };
};

const summarizeInstallability = (kpi) => {
  const value = kpi?.kpis?.installability?.installSuccessRatePct;
  const verifyPassed = kpi?.kpis?.installability?.verifyPassed;
  const status = verifyPassed === false ? "risk" : "on track";
  return {
    target: ">= 95%",
    actual: toPct(value),
    status,
    notes: `verifyPassed=${verifyPassed === null || verifyPassed === undefined ? "n/a" : String(verifyPassed)}`,
  };
};

const summarizeTtfw = (kpi) => {
  const value = kpi?.kpis?.meanTimeToFirstWorkflowMinutes;
  const status = typeof value === "number" && value <= 120 ? "on track" : "watch";
  return {
    target: "<= 120 min",
    actual: typeof value === "number" ? `${value.toFixed(1)} min` : "n/a",
    status,
    notes: "Metric supplied via SG_APIS_KPI_TTFW_MINUTES when available.",
  };
};

const summarizeDocsDrift = (kpi) => {
  const value = kpi?.kpis?.docsDriftDefects;
  const status = typeof value === "number" && value <= 2 ? "on track" : "watch";
  return {
    target: "<= 2 defects",
    actual: toNumber(value),
    status,
    notes: "Metric supplied via SG_APIS_KPI_DOCS_DRIFT_DEFECTS when available.",
  };
};

const summarizeNpmTrend = (ecosystem) => {
  const packages = Array.isArray(ecosystem?.externalSignals?.npmPackages) ? ecosystem.externalSignals.npmPackages : [];
  const sgApis = packages.find((entry) => entry?.packageName === "sg-apis-mcp");
  if (sgApis === undefined) {
    return "sg-apis-mcp monthly downloads: n/a";
  }
  return `sg-apis-mcp monthly downloads: ${toNumber(sgApis.downloadsLastMonth)}`;
};

const render = (input) => {
  const reportDate = new Date().toISOString().slice(0, 10);
  const completion = summarizeWorkflowCompletion(input.benchmark);
  const slo = summarizeSloCompliance(input.benchmark);
  const installability = summarizeInstallability(input.kpi);
  const ttfw = summarizeTtfw(input.kpi);
  const docsDrift = summarizeDocsDrift(input.kpi);

  const policyStatus = input.kpi?.overallPolicyStatus ?? "n/a";
  const alertCount = Array.isArray(input.kpi?.alerts) ? input.kpi.alerts.length : 0;
  const repoCount = input.ecosystem?.externalSignals?.singaporeMcpSearch?.totalCount;
  const stackOverflowCount = input.ecosystem?.externalSignals?.stackoverflow?.tagInfo?.questionCount;

  return `# Quarterly Product Health Report

## Quarter

- Reporting window: \`${input.quarter}\`
- Prepared by: \`${input.owner}\`
- Published date: \`${reportDate}\`
- Generated from:
  - benchmark: \`${input.paths.benchmark}\`
  - ecosystem: \`${input.paths.ecosystem}\`
  - kpi: \`${input.paths.kpi}\`

## KPI Summary

| KPI | Target | Actual | Status | Notes |
| --- | --- | --- | --- | --- |
| Install success rate | ${installability.target} | ${installability.actual} | ${installability.status} | ${installability.notes} |
| Mean time to first successful workflow | ${ttfw.target} | ${ttfw.actual} | ${ttfw.status} | ${ttfw.notes} |
| Workflow completion rate | ${completion.target} | ${completion.actual} | ${completion.status} | ${completion.notes} |
| SLO compliance (availability/latency/freshness) | ${slo.target} | ${slo.actual} | ${slo.status} | ${slo.notes} |
| Documentation drift defects | ${docsDrift.target} | ${docsDrift.actual} | ${docsDrift.status} | ${docsDrift.notes} |

## Reliability And Security

- SLO trend summary: overall policy status \`${policyStatus}\` with \`${alertCount}\` active KPI alerts.
- Security backlog summary: add current vulnerability and patch SLA notes.
- Incident summary and postmortems: add quarter-specific incidents and links.
- CI flake/failure taxonomy changes: add notable regression patterns.

## Adoption And Ecosystem

- Package install and usage trend: ${summarizeNpmTrend(input.ecosystem)}.
- Ecosystem snapshot highlights: singapore MCP repo count \`${toNumber(repoCount)}\`; Stack Overflow MCP question count \`${toNumber(stackOverflowCount)}\`.
- Contributor activity and repeat-contributor rate: add quarter-specific contributor metrics.
- Support burden trend: add ticket volume and top issue categories.

## Governance And Ownership

- Ownership-matrix changes: verify [docs/ownership-matrix.json](./ownership-matrix.json) updates for this quarter.
- Deprecation actions and migration status: summarize actions from [docs/deprecation-policy.md](./deprecation-policy.md).
- Policy exceptions approved (if any): list approved exceptions and expiry dates.

## Next Quarter Priorities

1. Reduce active KPI breach/warning alerts that block release evidence.
2. Improve onboarding metrics (installability and time-to-first-workflow) using integration templates.
3. Keep ecosystem and benchmark snapshots aligned with release cadence.
`;
};

const main = () => {
  const args = parseArgs(process.argv.slice(2));
  const quarter = args.quarter ?? toQuarter(new Date());
  const output = args.output ?? resolve(root, "artifacts/reports/quarterly", `${quarter}.md`);

  const benchmark = readRequiredJson(args.benchmark, "benchmark");
  const ecosystem = readRequiredJson(args.ecosystem, "ecosystem");
  const kpi = readRequiredJson(args.kpi, "kpi");

  const markdown = render({
    quarter,
    owner: args.owner,
    benchmark,
    ecosystem,
    kpi,
    paths: {
      benchmark: args.benchmark,
      ecosystem: args.ecosystem,
      kpi: args.kpi,
    },
  });

  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, `${markdown}\n`, "utf8");
  process.stdout.write(`quarterly report draft written: ${output}\n`);
};

main();
