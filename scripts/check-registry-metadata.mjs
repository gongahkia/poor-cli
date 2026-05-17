#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");

const serverMetadata = JSON.parse(read("server.json"));
const glamaMetadata = JSON.parse(read("glama.json"));
const smitheryMetadata = read("smithery.yaml");
const readme = read("README.md");

const expectedToolCount = 109;
const expectedFamilyCount = 39;
const expectedInstall = "npm install && npm run build && node packages/mcp-server/dist/index.js";

if (!serverMetadata.description.includes(`${expectedToolCount} sg_* tools`)) {
  throw new Error(`server.json description must mention ${expectedToolCount} sg_* tools.`);
}

if (!serverMetadata.description.includes(`${expectedFamilyCount} catalog families`)) {
  throw new Error(`server.json description must mention ${expectedFamilyCount} catalog families.`);
}

if (!readme.includes(`${expectedToolCount} \`sg_*\` tools total across ${expectedFamilyCount} catalog families`)) {
  throw new Error("README surface snapshot is out of sync with registry metadata counts.");
}

if (!smitheryMetadata.includes("name: dude-mcp")) {
  throw new Error("smithery.yaml must keep the public Smithery name as dude-mcp.");
}

if (!smitheryMetadata.includes(`install: ${expectedInstall}`)) {
  throw new Error("smithery.yaml install command drifted from the local stdio package entrypoint.");
}

if (glamaMetadata.name !== "dude-mcp") {
  throw new Error("glama.json must keep the public Glama name as dude-mcp.");
}

if (glamaMetadata.repository !== "https://github.com/gongahkia/dude") {
  throw new Error("glama.json repository must point at the canonical GitHub repository.");
}

if (glamaMetadata.install !== expectedInstall) {
  throw new Error("glama.json install command drifted from the local stdio package entrypoint.");
}

process.stdout.write("registry metadata check passed\n");
