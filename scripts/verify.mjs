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

const runNodeScript = (label, scriptPath, env = process.env) => {
  process.stdout.write(`\n==> ${label}\n`);
  execFileSync(process.execPath, [scriptPath], {
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
runNodeScript("diagnostics", "./scripts/dev-diagnostics.mjs");
runNodeScript("server metadata parity", "./scripts/check-server-metadata.mjs");
runNodeScript("live surface check", "./scripts/check-live-surface.mjs");
runNodeScript("openapi parity", "./scripts/check-openapi.mjs");
runNodeScript("docs parity", "./scripts/check-docs-parity.mjs");
runNodeScript("governance policy", "./scripts/check-governance.mjs");
runNodeScript("housing rules freshness", "./scripts/check-housing-rules-freshness.mjs");
run("template smoke", ["run", "test:smoke:templates"], testEnv);
run("profile smoke", ["run", "test:smoke:profiles"], testEnv);
run("test", ["test"], testEnv);

if (process.env.SG_APIS_SKIP_PACKAGING_SMOKE === "1") {
  process.stdout.write("\n==> packaging smoke (skipped via SG_APIS_SKIP_PACKAGING_SMOKE=1)\n");
} else {
  run("packaging smoke", ["run", "test:smoke:packaging"], testEnv);
}
