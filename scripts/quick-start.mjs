#!/usr/bin/env node
import { execSync } from "node:child_process";

const run = (cmd) => {
  console.log(`> ${cmd}`);
  execSync(cmd, { stdio: "inherit", cwd: process.cwd() });
};

const PUBLIC_ONLY = process.argv.includes("--public");

console.log("=== sg-apis-mcp quick start ===\n");

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
  if (PUBLIC_ONLY) {
    console.error("public smoke failed; run npm run diagnostics to inspect runtime and catalog parity.");
  } else {
    console.error("configure OneMap, URA, and LTA credentials via env vars or the local keystore, then retry.");
    console.error("for no-credential onboarding, run: npm run quick-start -- --public");
  }
  process.exit(1);
}

console.log("\n=== done! ===");
console.log("\nnext steps:");
console.log(`  npm run ${PUBLIC_ONLY ? "test:smoke:public" : "test:smoke:live"}`);
if (!PUBLIC_ONLY) {
  console.log("  npm run test:smoke:public");
}
console.log("  npx tsx examples/integration/basic-client.ts");
