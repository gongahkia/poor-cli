#!/usr/bin/env node
// quick-start: build, start mock server, run one brief workflow, print output
// usage: node scripts/quick-start.mjs [profile]
// profiles: business, property, macro, transport, environment, civic, architecture, healthcare, hotel, sector-business (default: property)
import { execSync, spawn } from "node:child_process";
import { setTimeout } from "node:timers/promises";

const profile = process.argv[2] ?? "property";
const VALID = ["business", "property", "macro", "transport", "environment", "civic", "architecture", "healthcare", "hotel", "sector-business"];
if (!VALID.includes(profile)) {
  console.error(`invalid profile: ${profile}. valid: ${VALID.join(", ")}`);
  process.exit(1);
}

const run = (cmd) => {
  console.log(`> ${cmd}`);
  execSync(cmd, { stdio: "inherit", cwd: process.cwd() });
};

console.log("=== sg-apis-mcp quick start ===\n");

// 1. build
console.log("[1/4] building...");
try {
  run("npm run build");
} catch {
  console.error("build failed. run 'npm install' first?");
  process.exit(1);
}

// 2. start mock server
console.log("\n[2/4] starting mock server...");
const mock = spawn("node", ["packages/mcp-server/dist/__tests__/mock-server/index.js"], {
  stdio: "pipe",
  env: { ...process.env, PORT: "9876" },
});
let mockReady = false;
mock.stdout.on("data", (d) => {
  if (d.toString().includes("listening")) mockReady = true;
});
mock.stderr.on("data", (d) => process.stderr.write(d));

// wait for mock server
for (let i = 0; i < 20; i++) {
  await setTimeout(250);
  if (mockReady) break;
}
if (!mockReady) {
  // give it a moment more, then proceed anyway
  await setTimeout(1000);
}

// 3. run demo
console.log(`\n[3/4] running ${profile} demo...\n`);
try {
  run(`MOCK_API_BASE_URL=http://localhost:9876 SG_APIS_LOG_LEVEL=warn npm run demo:mcp -- ${profile}`);
} catch (err) {
  console.error("demo failed:", err.message);
}

// 4. cleanup
console.log("\n[4/4] cleaning up...");
mock.kill();
console.log("\n=== done! ===");
console.log(`\nwant to explore more? try:`);
console.log(`  npm run demo:mcp -- business`);
console.log(`  npm run demo:mcp -- architecture`);
console.log(`  npm run demo:mcp -- healthcare`);
console.log(`  npm run demo:mcp -- hotel`);
console.log(`  npm run demo:mcp -- sector-business`);
console.log(`  npm run demo:mcp -- transport`);
console.log(`  npm run demo:mcp -- civic`);
console.log(`  npx tsx examples/integration/basic-client.ts`);
