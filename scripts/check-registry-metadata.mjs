#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");

const serverMetadata = JSON.parse(read("server.json"));
const glamaMetadata = JSON.parse(read("glama.json"));
const smitheryMetadata = read("smithery.yaml");
const readme = read("README.md");

const expectedInstall = "npm install && npm run build && node packages/mcp-server/dist/index.js";
const expectedDescription = "Swee SG MCP gateway for policy-governed Singapore public-data tools";

if (!serverMetadata.description.includes(expectedDescription)) {
  throw new Error("server.json description must describe the Swee SG runtime.");
}

if (!readme.includes("Swee Shield") || !readme.includes("Swee Pulse")) {
  throw new Error("README must describe the Swee Shield and Swee Pulse product surfaces.");
}

if (!smitheryMetadata.includes("name: swee-sg")) {
  throw new Error("smithery.yaml must use the Swee SG package name.");
}

if (!smitheryMetadata.includes(`install: ${expectedInstall}`)) {
  throw new Error("smithery.yaml install command drifted from the local stdio package entrypoint.");
}

if (glamaMetadata.name !== "swee-sg") {
  throw new Error("glama.json must use the Swee SG package name.");
}

if (glamaMetadata.repository !== "https://github.com/gongahkia/swee-sg") {
  throw new Error("glama.json repository must point at the canonical GitHub repository.");
}

if (glamaMetadata.install !== expectedInstall) {
  throw new Error("glama.json install command drifted from the local stdio package entrypoint.");
}

process.stdout.write("registry metadata check passed\n");
