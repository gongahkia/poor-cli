import { accessSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");
const PUBLIC_ONLY = process.argv.includes("--public-only");

const getText = (items) => {
  const text = items.find((item) => typeof item?.text === "string")?.text;
  if (text === undefined) {
    throw new Error("Expected text content from MCP response.");
  }
  return text;
};

const getStructuredPayload = (result) => {
  if ("structuredContent" in result && result.structuredContent !== undefined) {
    return result.structuredContent;
  }
  return JSON.parse(getText(result.content));
};

const callToolPayload = async (client, name, args) => {
  const result = await client.callTool({ name, arguments: args });
  return getStructuredPayload(result);
};

const readJsonResource = async (client, uri) => {
  const resource = await client.readResource({ uri });
  const text = resource.contents.find((content) => "text" in content && typeof content.text === "string")?.text;
  if (text === undefined) {
    throw new Error(`${uri} did not return text content.`);
  }
  return JSON.parse(text);
};

const main = async () => {
  accessSync(serverEntry);
  const smokeStateDir = mkdtempSync(resolve(tmpdir(), "swee-sg-smoke-"));

  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: process.env["SG_APIS_LOG_LEVEL"] ?? "error",
      SG_APIS_STATE_DIR: smokeStateDir,
    },
    stderr: "pipe",
  });

  const stderrChunks = [];
  transport.stderr?.on("data", (chunk) => {
    stderrChunks.push(String(chunk));
  });

  const client = new Client(
    { name: "swee-sg-smoke", version: "0.1.0" },
    { capabilities: {} },
  );

  const serverLogs = () => {
    const joined = stderrChunks.join("").trim();
    return joined === "" ? "" : `\nServer stderr:\n${joined}`;
  };

  try {
    await client.connect(transport);

    const tools = await client.listTools();
    const toolNames = new Set(tools.tools.map((tool) => tool.name));
    for (const required of ["swee_pulse_snapshot", "swee_pulse_explain", "swee_shield_scan_tools", "swee_shield_audit_lookup"]) {
      if (!toolNames.has(required)) {
        throw new Error(`MCP tool surface is missing ${required}.`);
      }
    }
    for (const removed of ["sg_query", "sg_business_dossier", "sg_cdd_report", "sg_resolve_counterparty"]) {
      if (toolNames.has(removed)) {
        throw new Error(`MCP tool surface still exposes removed CDD tool ${removed}.`);
      }
    }
    process.stdout.write(`- tool surface: ${tools.tools.length} tools\n`);

    const runtimeCatalog = await readJsonResource(client, "sg://runtime");
    if (runtimeCatalog.schemaVersion !== "swee-runtime/v1") {
      throw new Error(`Unexpected runtime schema: ${JSON.stringify(runtimeCatalog.schemaVersion)}`);
    }
    process.stdout.write("- runtime catalog: ok\n");

    const scanPayload = await callToolPayload(client, "swee_shield_scan_tools", {});
    if (typeof scanPayload.scannedTools !== "number" || !Array.isArray(scanPayload.findings)) {
      throw new Error("swee_shield_scan_tools did not return scanner metadata.");
    }
    process.stdout.write("- shield scanner: ok\n");

    if (!PUBLIC_ONLY) {
      const explainPayload = await callToolPayload(client, "swee_pulse_explain", { focus: "all" });
      if (explainPayload.aiUsed !== false || typeof explainPayload.explanation !== "string") {
        throw new Error("swee_pulse_explain did not return deterministic explain output.");
      }
      process.stdout.write("- pulse explain: ok\n");
    }

    const auditPayload = await callToolPayload(client, "swee_shield_audit_lookup", { limit: 10 });
    if (!Array.isArray(auditPayload.records)) {
      throw new Error("swee_shield_audit_lookup did not return audit records.");
    }
    process.stdout.write("- shield audit lookup: ok\n");

    process.stdout.write(PUBLIC_ONLY ? "public smoke test passed\n" : "live smoke test passed\n");
  } catch (error) {
    throw new Error(`${error instanceof Error ? error.message : String(error)}${serverLogs()}`);
  } finally {
    await client.close().catch(() => undefined);
    rmSync(smokeStateDir, { recursive: true, force: true });
  }
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.stderr.write("Run npm run build first; use npm run diagnostics for catalog parity context.\n");
  process.exit(1);
});
