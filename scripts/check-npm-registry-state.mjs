#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const packagePaths = [
  "packages/shared/package.json",
  "packages/mcp-server/package.json",
  "packages/sdk/package.json",
];

const mode = (
  process.env["DUDE_NPM_REGISTRY_MODE"]
  ?? process.env["SG_APIS_NPM_REGISTRY_MODE"]
  ?? "readiness"
).trim();

if (mode !== "readiness" && mode !== "published") {
  throw new Error(`Unsupported npm registry mode "${mode}". Use readiness or published.`);
}

const readJson = (path) => JSON.parse(readFileSync(resolve(root, path), "utf8"));
const read = (path) => readFileSync(resolve(root, path), "utf8");

const packages = packagePaths.map((path) => {
  const pkg = readJson(path);
  return { name: pkg.name, version: pkg.version, path };
});

const viewVersion = (packageName) => {
  try {
    return {
      state: "published",
      version: execFileSync("npm", ["view", packageName, "version", "--json"], {
        cwd: root,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      }).trim().replace(/^"|"$/g, ""),
    };
  } catch (error) {
    const stderr = String(error.stderr ?? "");
    const stdout = String(error.stdout ?? "");
    const output = `${stdout}\n${stderr}`;
    if (output.includes("E404") || output.includes("404 Not Found")) {
      return { state: "unpublished" };
    }
    throw new Error(`Unable to check ${packageName} on npm: ${output.trim() || error.message}`);
  }
};

const readinessDocs = [
  read("docs/npm-publish-readiness.md"),
  read("docs/sdk-publish-readiness.md"),
  read("packages/mcp-server/README.md"),
  read("packages/sdk/README.md"),
].join("\n");

if (mode === "readiness") {
  for (const phrase of [
    "no public version exists yet",
    "Do not represent `@dude/mcp` as published",
    "After the package is public on npm",
    "should not be published to npm until",
  ]) {
    if (!readinessDocs.includes(phrase)) {
      throw new Error(`Readiness mode requires docs to state unpublished package status. Missing phrase: ${phrase}`);
    }
  }
}

const records = packages.map((pkg) => ({ ...pkg, registry: viewVersion(pkg.name) }));
const unpublished = records.filter((record) => record.registry.state === "unpublished");
const mismatched = records.filter(
  (record) => record.registry.state === "published" && record.registry.version !== record.version,
);

if (mode === "published" && unpublished.length > 0) {
  throw new Error(
    `Published mode requires all packages on npm. Missing: ${unpublished.map((record) => record.name).join(", ")}. `
    + "Publish missing packages or run in DUDE_NPM_REGISTRY_MODE=readiness before first release.",
  );
}

if (mismatched.length > 0) {
  throw new Error(
    `Published package versions do not match workspace versions: ${
      mismatched.map((record) => `${record.name} npm=${record.registry.version} local=${record.version}`).join("; ")
    }. Bump versions or publish matching packages before release.`,
  );
}

if (mode === "readiness" && unpublished.length > 0) {
  process.stdout.write(
    `npm registry readiness OK: ${unpublished.map((record) => record.name).join(", ")} not published yet; docs describe first-publish blocker.\n`,
  );
} else {
  process.stdout.write(
    `npm registry availability OK: ${records.map((record) => `${record.name}@${record.version}`).join(", ")}.\n`,
  );
}
