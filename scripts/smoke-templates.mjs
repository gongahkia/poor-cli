import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

const run = (label, args, extraEnv = {}) => {
  process.stdout.write(`\n==> ${label}\n`);
  execFileSync("npx", args, {
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: process.env.SG_APIS_LOG_LEVEL ?? "error",
      ...extraEnv,
    },
    stdio: "inherit",
  });
};

run("ui state template", ["tsx", "examples/integration/ui-state-template.ts"]);
run("scheduled monitor template (dry-run)", ["tsx", "examples/integration/scheduled-monitor-template.ts", "--dry-run"]);
run(
  "success context IDs template",
  ["tsx", "examples/integration/success-context-ids-template.ts"],
  { SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS: "1" },
);
