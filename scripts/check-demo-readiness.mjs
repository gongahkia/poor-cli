import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const failures = [];

const read = (path) => readFileSync(resolve(root, path), "utf8");
const exists = (path) => {
  try {
    statSync(resolve(root, path));
    return true;
  } catch {
    return false;
  }
};
const requireFile = (path) => {
  if (!exists(path)) failures.push(`${path} is missing`);
};
const requireText = (path, pattern, label) => {
  const text = read(path);
  if (!pattern.test(text)) failures.push(`${path} missing ${label}`);
};

for (const path of [
  "LICENSE",
  "README.md",
  ".env.example",
  "architecture_diagram.md",
  "docs/submission/significant-update.md",
  "docs/submission/demo-script.md",
  "docs/submission/claims-audit.md",
  "packages/mcp-server/src/shield/__tests__/runtime-demo-fixtures.test.ts",
  "packages/mcp-server/src/upstreams/splunk/__tests__/fixtures/demo-events.json",
  "scripts/check-submission-claims.mjs",
  "scripts/splunk-live-smoke.mjs",
]) {
  requireFile(path);
}

requireText("LICENSE", /MIT License/, "MIT license text");
requireText("README.md", /Splunk Demo Paths/, "Splunk demo section");
requireText("README.md", /SPLUNK_MCP_URL/, "Splunk URL env documentation");
requireText("README.md", /SPLUNK_MCP_TOKEN/, "Splunk token env documentation");
requireText("README.md", /runtime-demo-fixtures\.test\.ts/, "token-free fixture demo command");
requireText(".env.example", /SWEE_SHIELD_RUNTIME_SCAN_MODE=neutralize/, "runtime scan mode env");
requireText("architecture_diagram.md", /Splunk MCP Server/, "Splunk MCP data-flow node");
requireText("architecture_diagram.md", /Runtime output scanner/, "runtime scanner data-flow node");
requireText("architecture_diagram.md", /does not provide deterministic replay/, "replay limitation");
requireText("docs/submission/demo-script.md", /under 3 minutes/i, "demo duration note");
requireText("docs/submission/demo-script.md", /fake demo events, not live Splunk output/i, "synthetic fixture disclaimer");
requireText("docs/submission/claims-audit.md", /Forbidden Claims/, "forbidden claims section");

const fixture = JSON.parse(read("packages/mcp-server/src/upstreams/splunk/__tests__/fixtures/demo-events.json"));
if (!/Synthetic Splunk demo events/i.test(String(fixture.fixtureNotice ?? ""))) {
  failures.push("demo fixture missing synthetic notice");
}
if (!/Not live Splunk data/i.test(String(fixture.fixtureNotice ?? ""))) {
  failures.push("demo fixture missing not-live-Splunk notice");
}

const packageJson = JSON.parse(read("package.json"));
for (const scriptName of [
  "submission:claims:check",
  "submission:readiness:check",
  "splunk:smoke:live",
]) {
  if (typeof packageJson.scripts?.[scriptName] !== "string") {
    failures.push(`package.json missing ${scriptName}`);
  }
}

if (failures.length > 0) {
  process.stderr.write("Demo readiness check failed:\n");
  for (const failure of failures) process.stderr.write(`- ${failure}\n`);
  process.exit(1);
}

process.stdout.write("demo readiness check passed\n");
