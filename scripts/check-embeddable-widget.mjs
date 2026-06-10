import { readFile } from "node:fs/promises";

const files = [
  "examples/embeddable-widget/swee-pulse-widget.js",
  "examples/embeddable-widget/widget-frame.html",
  "examples/embeddable-widget/demo.html",
  "examples/embeddable-widget/README.md",
];

const read = async (path) => [path, await readFile(path, "utf8")];
const entries = Object.fromEntries(await Promise.all(files.map(read)));
const widget = entries["examples/embeddable-widget/swee-pulse-widget.js"];
const readme = entries["examples/embeddable-widget/README.md"];
const frame = entries["examples/embeddable-widget/widget-frame.html"];

const checks = [
  ["defines custom element", widget.includes('customElements.define("swee-pulse-widget"')],
  ["calls Pulse endpoint", widget.includes("/api/v1/pulse/snapshot")],
  ["supports gateway-url", widget.includes('"gateway-url"')],
  ["supports auth token", widget.includes("Authorization") && readme.includes("short-lived token")],
  ["supports focus scoping", widget.includes('"focus"') && readme.includes("all`, `mobility`, or `weather")],
  ["surfaces source freshness", widget.includes("Sources:")],
  ["surfaces gaps", widget.includes("Gaps:")],
  ["documents origin controls", readme.includes("CORS allowlist")],
  ["documents iframe API", frame.includes("gatewayUrl") && frame.includes("focus") && readme.includes("Iframe Wrapper")],
  ["documents white-label CSS", readme.includes("--swee-widget-accent")],
];

const failed = checks.filter(([, passed]) => !passed);
if (failed.length > 0) {
  console.error("Embeddable widget check failed:");
  for (const [label] of failed) {
    console.error(`- ${label}`);
  }
  process.exit(1);
}

console.log(`Embeddable widget OK: ${checks.length} integration checks passed.`);
