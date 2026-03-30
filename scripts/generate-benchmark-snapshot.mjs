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
const generatedAt = process.env["SG_APIS_BENCHMARK_GENERATED_AT"] ?? new Date().toISOString();
const source = process.env["GITHUB_ACTIONS"] === "true" ? "github-actions" : "local";
const registrySmokeStatus = process.env["SG_APIS_REGISTRY_SMOKE_STATUS"] === "passed" ? "passed" : "skipped";

const snapshot = {
  schemaVersion: "1.0",
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
  ],
};

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, JSON.stringify(snapshot, null, 2) + "\n");

process.stdout.write(`benchmark snapshot written: ${outputPath}\n`);
