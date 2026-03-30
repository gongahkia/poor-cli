#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const serverMetadata = JSON.parse(readFileSync(resolve(root, "server.json"), "utf8"));
const serverPkg = JSON.parse(readFileSync(resolve(root, "packages/mcp-server/package.json"), "utf8"));

if (serverMetadata.$schema !== "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json") {
  throw new Error("server.json is missing the current MCP registry schema URL.");
}

if (serverMetadata.name !== serverPkg.mcpName) {
  throw new Error("server.json name must match packages/mcp-server/package.json#mcpName.");
}

if (serverMetadata.version !== serverPkg.version) {
  throw new Error("server.json version must match packages/mcp-server/package.json version.");
}

if (!Array.isArray(serverMetadata.packages) || serverMetadata.packages.length === 0) {
  throw new Error("server.json must declare at least one package install source.");
}

if (!Array.isArray(serverMetadata.remotes) || serverMetadata.remotes.length === 0) {
  throw new Error("server.json must declare at least one remote MCP endpoint.");
}

for (const remote of serverMetadata.remotes) {
  if (remote.type !== "streamable-http") {
    throw new Error(`server.json remote ${remote.url ?? "<missing-url>"} must declare streamable-http transport.`);
  }

  if (typeof remote.url !== "string" || remote.url.trim() === "") {
    throw new Error("server.json remote entries must include a non-empty url.");
  }

  const remoteUrl = new URL(remote.url);
  if (remoteUrl.pathname !== "/mcp") {
    throw new Error(`server.json remote ${remote.url} must point directly at /mcp.`);
  }
}

const npmPackage = serverMetadata.packages.find((pkg) => pkg.registryType === "npm");
if (npmPackage?.identifier !== serverPkg.name) {
  throw new Error("server.json npm package identifier must match the published npm package name.");
}

const ociPackage = serverMetadata.packages.find((pkg) => pkg.registryType === "oci");
if (ociPackage?.identifier !== "ghcr.io/gongahkia/sg-apis-mcp") {
  throw new Error("server.json OCI package identifier must match the published GHCR image.");
}

for (const pkg of serverMetadata.packages) {
  if (pkg.version !== serverPkg.version) {
    throw new Error(`server.json package ${pkg.identifier} is pinned to ${pkg.version}, expected ${serverPkg.version}.`);
  }
  if (pkg.transport?.type !== "stdio") {
    throw new Error(`server.json package ${pkg.identifier} must declare stdio transport.`);
  }
}

process.stdout.write("server metadata check passed\n");
