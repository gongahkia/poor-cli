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
  SG_APIS_LOG_LEVEL: process.env.SG_APIS_LOG_LEVEL ?? "error",
};

run("lint", ["run", "lint"]);
run("build", ["run", "build"]);
run("server metadata parity", ["exec", "--", "node", "./scripts/check-server-metadata.mjs"]);
run("live surface check", ["exec", "--", "node", "./scripts/check-live-surface.mjs"]);
run("openapi parity", ["exec", "--", "node", "./scripts/check-openapi.mjs"]);
run("docs parity", ["exec", "--", "node", "./scripts/check-docs-parity.mjs"]);
run("test", ["test"], testEnv);
run("packaging smoke", ["run", "test:smoke:packaging"]);
