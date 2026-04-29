// release:dryrun - publish-equivalent proof without touching the npm registry.
// 1. npm pack each publishable workspace into artifacts/release/<commit>.
// 2. Install the tarballs into a fresh temp project (simulates `npx sg-apis-mcp`).
// 3. Boot the server bin, list tools, and read sg://recipes.
// 4. Write a release-receipt.json so a maintainer can see exactly what would publish.
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, copyFileSync, statSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, basename } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const commitSha = (() => {
  try {
    return execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
  } catch {
    return "uncommitted";
  }
})();
const releaseDir = resolve(root, "artifacts", "release", commitSha);
const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-release-"));
const npmCacheDir = join(tempDir, "npm-cache");
const env = { ...process.env, NPM_CONFIG_CACHE: npmCacheDir, npm_config_cache: npmCacheDir };

mkdirSync(releaseDir, { recursive: true });

const run = (args, cwd = root) =>
  execFileSync("npm", args, { cwd, env, encoding: "utf8", maxBuffer: 10 * 1024 * 1024 }).trim();

const pack = (workspace) => {
  process.stdout.write(`Packing ${workspace}...\n`);
  const output = run(["pack", "--json", "--workspace", workspace]);
  const [info] = JSON.parse(output);
  const sourceTarball = resolve(root, info.filename);
  const archived = resolve(releaseDir, basename(info.filename));
  copyFileSync(sourceTarball, archived);
  rmSync(sourceTarball);
  return { workspace, name: info.name, version: info.version, filename: basename(info.filename), bytes: statSync(archived).size, archived };
};

const main = async () => {
  const sharedPack = pack("packages/shared");
  const serverPack = pack("packages/mcp-server");

  process.stdout.write("Installing packed tarballs into temp project...\n");
  writeFileSync(join(tempDir, "package.json"), JSON.stringify({ name: "sg-apis-release-dryrun", private: true, type: "module" }, null, 2));
  run(["install", "--no-package-lock", sharedPack.archived], tempDir);
  run(["install", "--no-package-lock", serverPack.archived], tempDir);

  process.stdout.write("Booting server bin and probing surface...\n");
  const transport = new StdioClientTransport({
    command: join(tempDir, "node_modules", ".bin", "sg-apis-mcp"),
    cwd: tempDir,
    env: { ...env, HOME: tempDir, SG_APIS_LOG_LEVEL: "error" },
    stderr: "pipe",
  });
  const client = new Client({ name: "release-dryrun", version: "0.1.0" }, { capabilities: {} });
  let surface;
  try {
    await client.connect(transport);
    const tools = await client.listTools();
    const resources = await client.listResources();
    const recipes = await client.readResource({ uri: "sg://recipes" });
    surface = {
      serverInfo: client.getServerVersion(),
      toolCount: (tools.tools ?? []).length,
      resourceCount: (resources.resources ?? []).length,
      recipeCount: (() => {
        try {
          const text = (recipes.contents ?? []).find((c) => typeof c.text === "string")?.text ?? "[]";
          const parsed = JSON.parse(text);
          return Array.isArray(parsed) ? parsed.length : null;
        } catch {
          return null;
        }
      })(),
    };
  } finally {
    await client.close().catch(() => undefined);
  }

  const receipt = {
    schemaVersion: "1.0",
    generatedAt: new Date().toISOString(),
    commitSha,
    tarballs: [
      { ...sharedPack, archived: undefined, archivedRelative: `artifacts/release/${commitSha}/${sharedPack.filename}` },
      { ...serverPack, archived: undefined, archivedRelative: `artifacts/release/${commitSha}/${serverPack.filename}` },
    ],
    surface,
    notes: [
      "This receipt proves that npx-equivalent install of the packed tarballs boots the server and exposes the expected surface.",
      "It does not publish to the npm registry. Use `npm publish --workspace <pkg>` once the receipt is reviewed.",
    ],
  };
  const receiptPath = resolve(releaseDir, "release-receipt.json");
  writeFileSync(receiptPath, JSON.stringify(receipt, null, 2));
  process.stdout.write(`Wrote ${receiptPath}\n`);
  process.stdout.write(`Surface: ${surface.toolCount} tools, ${surface.resourceCount} resources, ${surface.recipeCount ?? "?"} recipes.\n`);
};

main().catch((error) => {
  process.stderr.write(`release:dryrun failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
}).finally(() => {
  try { rmSync(tempDir, { recursive: true, force: true }); } catch { /* noop */ }
});
