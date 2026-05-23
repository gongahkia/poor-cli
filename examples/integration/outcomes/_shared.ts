// Shared helpers for outcome example scripts. Kept dependency-free so each outcome
// script remains a single runnable surface for adopters.
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

type TextContent = Readonly<{ type?: string; text?: string }>;

const currentDir = dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = resolve(currentDir, "..", "..", "..");
export const SERVER_ENTRY = resolve(REPO_ROOT, "packages/mcp-server/dist/index.js");

export const getText = (items: readonly TextContent[]): string => {
  const text = items.find((item) => typeof item.text === "string")?.text;
  if (text === undefined) {
    throw new Error("Expected text content from MCP response.");
  }
  return text;
};

export const callToolPayload = async <T>(
  client: Client,
  name: string,
  args: Readonly<Record<string, unknown>>,
): Promise<T> => {
  const result = await client.callTool({ name, arguments: args });
  if ("structuredContent" in result && result.structuredContent !== undefined) {
    const sc = result.structuredContent as Readonly<Record<string, unknown>>;
    if ("record" in sc) {
      return sc["record"] as T;
    }
    return sc as T;
  }
  return JSON.parse(getText(result.content as readonly TextContent[])) as T;
};

export const connectClient = async (label: string): Promise<Client> => {
  const transport = new StdioClientTransport({
    command: "node",
    args: [SERVER_ENTRY],
    cwd: REPO_ROOT,
    env: { ...process.env, SG_APIS_LOG_LEVEL: "error" },
  });
  const client = new Client({ name: label, version: "0.1.0" });
  await client.connect(transport);
  return client;
};

type PulseSnapshot = Readonly<{
  generatedAt?: string;
  signals?: readonly Readonly<{
    title?: string;
    severity?: string;
    sourceTool?: string;
    recommendedAction?: string;
  }>[];
  sourceHealth?: readonly Readonly<{
    sourceTool?: string;
    status?: string;
    recordCount?: number;
  }>[];
  gaps?: readonly Readonly<{ code?: string; message?: string }>[];
}>;

export const renderPulseSnapshot = (label: string, snapshot: PulseSnapshot): void => {
  console.log(`\n=== ${label} :: ${snapshot.generatedAt ?? "(no timestamp)"} ===`);
  console.log("Signals:");
  for (const signal of snapshot.signals ?? []) {
    console.log(`  - [${signal.severity ?? "unknown"}] ${signal.title ?? "(untitled)"} (${signal.sourceTool ?? "unknown source"})`);
  }
  if (snapshot.sourceHealth !== undefined && snapshot.sourceHealth.length > 0) {
    console.log("Source health:");
    for (const source of snapshot.sourceHealth) {
      console.log(`  - ${source.sourceTool ?? "unknown"}: ${source.status ?? "unknown"} (${source.recordCount ?? 0} rows)`);
    }
  }
  if (snapshot.gaps !== undefined && snapshot.gaps.length > 0) {
    console.log("Gaps:");
    for (const gap of snapshot.gaps) {
      console.log(`  - ${gap.code ?? "UNKNOWN_GAP"}: ${gap.message ?? ""}`);
    }
  }
};

export const exitOnError = (error: unknown): never => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
};
