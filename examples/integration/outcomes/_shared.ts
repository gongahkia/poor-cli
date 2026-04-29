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

type BriefEnvelope = Readonly<{
  title?: string;
  summary?: readonly Readonly<{ label: string; value: unknown; source: string }>[];
  gaps?: readonly Readonly<{ code: string; message: string }>[];
  freshness?: readonly Readonly<{ source: string; observedAt: string; upstreamTimestamp: string | null }>[];
  riskFlags?: readonly Readonly<{ code: string; severity: string; message: string; source: string }>[];
  nextChecks?: readonly Readonly<{ tool: string; reason: string; input: Readonly<Record<string, unknown>> }>[];
}>;

export const renderBrief = (label: string, brief: BriefEnvelope): void => {
  console.log(`\n=== ${label} :: ${brief.title ?? "(no title)"} ===`);
  console.log("Summary:");
  for (const item of brief.summary ?? []) {
    console.log(`  - ${item.label}: ${JSON.stringify(item.value)} [${item.source}]`);
  }
  if (brief.riskFlags !== undefined && brief.riskFlags.length > 0) {
    console.log("Risk flags:");
    for (const flag of brief.riskFlags) {
      console.log(`  - [${flag.severity.toUpperCase()}] ${flag.code}: ${flag.message}`);
    }
  }
  if (brief.gaps !== undefined && brief.gaps.length > 0) {
    console.log("Gaps:");
    for (const gap of brief.gaps) {
      console.log(`  - ${gap.code}: ${gap.message}`);
    }
  }
  if (brief.nextChecks !== undefined && brief.nextChecks.length > 0) {
    console.log("Next checks (UI buttons):");
    for (const check of brief.nextChecks) {
      console.log(`  - ${check.tool}: ${check.reason}`);
    }
  }
  if (brief.freshness !== undefined) {
    const stale = brief.freshness.filter((f) => f.upstreamTimestamp === null);
    if (stale.length > 0) {
      console.log(`Freshness warnings: ${stale.length} source(s) without upstream timestamp.`);
    }
  }
};

export const exitOnError = (error: unknown): never => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
};
