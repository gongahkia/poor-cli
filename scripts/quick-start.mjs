#!/usr/bin/env node
import { execSync } from "node:child_process";

const run = (cmd) => {
  console.log(`> ${cmd}`);
  execSync(cmd, { stdio: "inherit", cwd: process.cwd() });
};

const PUBLIC_ONLY = process.argv.includes("--public");
const AUTO_DIAGNOSTICS = !process.argv.includes("--no-diagnostics-on-fail");

console.log("=== Dude MCP quick start ===\n");

console.log("[1/2] building...");
try {
  run("npm run build");
} catch {
  console.error("build failed. run 'npm install' first?");
  process.exit(1);
}

console.log(`\n[2/2] running ${PUBLIC_ONLY ? "public" : "live"} smoke...`);
try {
  run(PUBLIC_ONLY ? "npm run test:smoke:public" : "npm run test:smoke:live");
} catch (error) {
  console.error("quick start failed:", error instanceof Error ? error.message : String(error));
  if (AUTO_DIAGNOSTICS) {
    console.error("running diagnostics to capture immediate repo/runtime parity context...");
    try {
      run("npm run diagnostics");
    } catch {
      console.error("diagnostics failed; inspect logs and run npm run diagnostics manually.");
    }
  }
  if (PUBLIC_ONLY) {
    console.error("public smoke failed; run npm run diagnostics to inspect runtime and catalog parity.");
  } else {
    console.error("configure optional CDD provider credentials via env vars when your smoke target requires them, then retry.");
    console.error("for no-credential onboarding, run: npm run quick-start -- --public");
  }
  console.error("if the failure response includes traceId/requestId, use sg_trace_lookup or sg_request_lookup to inspect local audit context.");
  process.exit(1);
}

console.log("\n=== done! ===");
console.log("\nnext steps:");
console.log(`  npm run ${PUBLIC_ONLY ? "test:smoke:public" : "test:smoke:live"}`);
if (!PUBLIC_ONLY) {
  console.log("  npm run test:smoke:public");
}
console.log("  npx tsx examples/integration/basic-client.ts");
