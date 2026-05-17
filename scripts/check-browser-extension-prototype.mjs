import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const extensionDir = resolve(root, "examples/browser-extension");
const manifest = JSON.parse(readFileSync(resolve(extensionDir, "manifest.json"), "utf8"));
const contentScript = readFileSync(resolve(extensionDir, "content-script.js"), "utf8");
const readme = readFileSync(resolve(extensionDir, "README.md"), "utf8");

const fail = (message) => {
  process.stderr.write(`browser extension prototype check failed: ${message}\n`);
  process.exit(1);
};

if (manifest.manifest_version !== 3) {
  fail("manifest must use Manifest V3");
}

if (!Array.isArray(manifest.content_scripts) || manifest.content_scripts.length !== 1) {
  fail("prototype must define exactly one content script");
}

if (!manifest.content_scripts[0].js.includes("content-script.js")) {
  fail("content script must include content-script.js");
}

if (!Array.isArray(manifest.host_permissions) || !manifest.host_permissions.every((item) => item.startsWith("http://localhost:"))) {
  fail("host permissions must stay limited to localhost origins in the prototype");
}

const firstFetch = contentScript.indexOf("fetch(");
const openPreview = contentScript.indexOf("async function openPreview");
if (firstFetch === -1 || openPreview === -1 || firstFetch < openPreview) {
  fail("network fetch must be click-triggered inside openPreview");
}

for (const required of ["UEN_PATTERN", "chrome.storage.sync", "No page data was sent before this click"]) {
  if (!contentScript.includes(required)) {
    fail(`content script must include ${required}`);
  }
}

for (const required of ["Supported Browsers", "Privacy And Permissions", "Limits"]) {
  if (!readme.includes(required)) {
    fail(`README must document ${required}`);
  }
}

process.stdout.write("browser extension prototype ok\n");
