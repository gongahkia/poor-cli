#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

const run = (label, args, env = process.env) => {
  process.stdout.write(`\n==> ${label}\n`);
  execFileSync("npm", args, {
    cwd: root,
    env,
    stdio: "inherit",
  });
};

const env = {
  ...process.env,
  SG_APIS_LOG_LEVEL: process.env["SG_APIS_LOG_LEVEL"] ?? "error",
};

run("verify", ["run", "verify"], env);
run("production dependency audit", ["run", "security:audit:prod"], env);
run(
  "benchmark snapshot",
  ["run", "benchmarks:snapshot", "--", "--output", "artifacts/benchmarks/latest.json", "--history-dir", "artifacts/benchmarks/history"],
  env,
);
run(
  "ecosystem snapshot",
  ["run", "ecosystem:snapshot", "--", "--output", "artifacts/ecosystem/latest.json", "--history-dir", "artifacts/ecosystem/history"],
  env,
);
run(
  "kpi dashboard",
  ["run", "kpis:dashboard", "--", "--benchmark", "artifacts/benchmarks/latest.json", "--ecosystem", "artifacts/ecosystem/latest.json", "--output", "artifacts/operations/latest.json", "--history-dir", "artifacts/operations/history"],
  env,
);
run(
  "release evidence check",
  ["run", "release:evidence", "--", "--benchmark", "artifacts/benchmarks/latest.json", "--ecosystem", "artifacts/ecosystem/latest.json", "--kpi", "artifacts/operations/latest.json"],
  env,
);
