#!/usr/bin/env node
import { execSync } from "node:child_process";

const run = (cmd) => {
  console.log(`> ${cmd}`);
  execSync(cmd, { stdio: "inherit", cwd: process.cwd() });
};

console.log("=== sg-apis-mcp quick start ===\n");

console.log("[1/2] building...");
try {
  run("npm run build");
} catch {
  console.error("build failed. run 'npm install' first?");
  process.exit(1);
}

console.log("\n[2/2] running live smoke...");
try {
  run("npm run test:smoke:live");
} catch (error) {
  console.error("quick start failed:", error instanceof Error ? error.message : String(error));
  console.error("configure OneMap, URA, and LTA credentials via env vars or the local keystore, then retry.");
  process.exit(1);
}

console.log("\n=== done! ===");
console.log("\nnext steps:");
console.log("  npm run test:smoke:live");
console.log("  npx tsx examples/integration/basic-client.ts");
