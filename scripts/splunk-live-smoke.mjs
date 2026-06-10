import { accessSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");
const url = process.env["SPLUNK_MCP_URL"]?.trim();
const token = process.env["SPLUNK_MCP_TOKEN"]?.trim();
const allowKeystore = process.env["SWEE_SPLUNK_SMOKE_ALLOW_KEYSTORE"] === "1";

if (url === undefined || url === "" || ((token === undefined || token === "") && !allowKeystore)) {
  process.stdout.write("Splunk live smoke skipped: set SPLUNK_MCP_URL and SPLUNK_MCP_TOKEN, or set SWEE_SPLUNK_SMOKE_ALLOW_KEYSTORE=1 for a configured splunk_mcp keystore token.\n");
  process.exit(0);
}

const getText = (items) => {
  const text = items.find((item) => typeof item?.text === "string")?.text;
  if (text === undefined) throw new Error("Expected text content from MCP response.");
  return text;
};

const getStructuredPayload = (result) => {
  if ("structuredContent" in result && result.structuredContent !== undefined) return result.structuredContent;
  return JSON.parse(getText(result.content));
};

const callToolPayload = async (client, name, args) => {
  const result = await client.callTool({ name, arguments: args });
  return getStructuredPayload(result);
};

const defaultSearchQuery = () => {
  const firstAllowed = process.env["SPLUNK_MCP_ALLOWED_INDEXES"]
    ?.split(",")
    .map((value) => value.trim())
    .find((value) => value !== "");
  return `index=${firstAllowed ?? "_internal"} | head 1`;
};

const main = async () => {
  accessSync(serverEntry);
  const smokeStateDir = token === undefined || token === "" ? null : mkdtempSync(resolve(tmpdir(), "swee-sg-splunk-smoke-"));
  const env = {
    ...process.env,
    SG_APIS_LOG_LEVEL: process.env["SG_APIS_LOG_LEVEL"] ?? "error",
    ...(smokeStateDir === null ? {} : { SG_APIS_STATE_DIR: smokeStateDir }),
  };
  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env,
    stderr: "pipe",
  });
  const stderrChunks = [];
  transport.stderr?.on("data", (chunk) => stderrChunks.push(String(chunk)));
  const client = new Client({ name: "swee-sg-splunk-live-smoke", version: "0.1.0" }, { capabilities: {} });
  const serverLogs = () => {
    const joined = stderrChunks.join("").trim();
    return joined === "" ? "" : `\nServer stderr:\n${joined}`;
  };

  try {
    await client.connect(transport);
    const tools = await client.listTools();
    const toolNames = new Set(tools.tools.map((tool) => tool.name));
    for (const required of ["splunk_list_indexes", "splunk_search", "swee_shield_audit_lookup"]) {
      if (!toolNames.has(required)) throw new Error(`MCP tool surface is missing ${required}.`);
    }
    process.stdout.write("- Splunk proxy tools: present\n");

    await callToolPayload(client, "splunk_list_indexes", { limit: 5, format: "json" });
    process.stdout.write("- splunk_list_indexes: ok\n");

    const query = process.env["SWEE_SPLUNK_SMOKE_QUERY"]?.trim() || defaultSearchQuery();
    await callToolPayload(client, "splunk_search", { query, limit: 1, format: "json" });
    process.stdout.write(`- splunk_search: ok (${query})\n`);

    const auditPayload = await callToolPayload(client, "swee_shield_audit_lookup", { toolName: "splunk_search", limit: 5 });
    const records = Array.isArray(auditPayload.records) ? auditPayload.records : [];
    if (records.length === 0) throw new Error("No splunk_search Shield audit row was recorded.");
    const latest = records[0];
    if (typeof latest.rawOutputHash !== "string" || typeof latest.outputHash !== "string") {
      throw new Error("Latest splunk_search audit row is missing raw/post output hashes.");
    }
    process.stdout.write("- Shield audit hash evidence: ok\n");
    process.stdout.write("Splunk live smoke passed\n");
  } catch (error) {
    throw new Error(`${error instanceof Error ? error.message : String(error)}${serverLogs()}`);
  } finally {
    await client.close().catch(() => undefined);
    if (smokeStateDir !== null) rmSync(smokeStateDir, { recursive: true, force: true });
  }
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.stderr.write("Run npm run build first. Without live Splunk credentials this script should skip, not fail.\n");
  process.exit(1);
});
