import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

const run = (label, command, args, extraEnv = {}) => {
  process.stdout.write(`\n==> ${label}\n`);
  execFileSync(command, args, {
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: process.env.SG_APIS_LOG_LEVEL ?? "error",
      ...extraEnv,
    },
    stdio: "inherit",
  });
};

run("ui state template", "npx", ["tsx", "examples/integration/ui-state-template.ts"]);
run("scheduled monitor template (dry-run)", "npx", ["tsx", "examples/integration/scheduled-monitor-template.ts", "--dry-run"]);
run(
  "success context IDs template",
  "npx",
  ["tsx", "examples/integration/success-context-ids-template.ts"],
  { SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS: "1" },
);
run("python backend worker template (dry-run)", "python3", ["examples/integration/backend-worker-template.py", "--dry-run"]);
run("python queue consumer template (dry-run)", "python3", ["examples/integration/queue-consumer-template.py", "--dry-run"]);
