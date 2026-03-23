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

const testEnv = {
  ...process.env,
  MOCK_API_BASE_URL: process.env.MOCK_API_BASE_URL ?? "http://localhost:0",
  SG_APIS_LOG_LEVEL: process.env.SG_APIS_LOG_LEVEL ?? "error",
};

run("lint", ["run", "lint"]);
run("build", ["run", "build"]);
run("docs parity", ["exec", "--", "node", "./scripts/check-docs-parity.mjs"]);
run("test", ["test"], testEnv);
run("packaging smoke", ["run", "test:smoke:packaging"], testEnv);
