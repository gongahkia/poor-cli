// Truthful TypeScript MCP client example for Swee SG.
// Run after `npm run build`:
//   npx tsx examples/integration/basic-client.ts
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

type TextContent = Readonly<{ text?: string }>;
type ResourceTextContent = Readonly<{ text?: string }>;

type RecipeCatalogEntry = Readonly<{
  name: string;
  prompt: string;
  fallbackTools: readonly string[];
  preferredEntrypoint: Readonly<{
    tool: string;
    input: Readonly<Record<string, unknown>>;
  }>;
}>;

type PulseSignal = Readonly<{
  severity: "info" | "watch" | "disrupted";
  title: string;
  sourceTool: string;
  recommendedAction: string;
}>;

type PulseToolPayload = Readonly<{
  snapshot: Readonly<{
    generatedAt: string;
    signals: readonly PulseSignal[];
    sourceHealth: readonly Readonly<{ sourceTool: string; status: string; recordCount: number }>[];
    gaps: readonly Readonly<{ code: string; message: string }>[];
  }>;
}>;

type ShieldScanPayload = Readonly<{
  scannedTools: number;
  findings: readonly unknown[];
}>;

const currentDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(currentDir, "..", "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");

const getText = (items: readonly TextContent[] | readonly ResourceTextContent[]): string => {
  const text = items.find((item) => typeof item.text === "string")?.text;
  if (text === undefined) {
    throw new Error("Expected text content from MCP response.");
  }
  return text;
};

const readJsonResource = async <T>(client: Client, uri: string): Promise<T> => {
  const resource = await client.readResource({ uri });
  return JSON.parse(getText(resource.contents as readonly ResourceTextContent[])) as T;
};

const callToolPayload = async <T>(
  client: Client,
  name: string,
  args: Readonly<Record<string, unknown>>,
): Promise<T> => {
  const result = await client.callTool({ name, arguments: args });
  if ("structuredContent" in result && result.structuredContent !== undefined) {
    return result.structuredContent as T;
  }
  return JSON.parse(getText(result.content as readonly TextContent[])) as T;
};

const main = async () => {
  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: "error",
    },
  });
  const client = new Client({ name: "swee-basic-client-example", version: "0.1.0" });

  await client.connect(transport);

  try {
    const recipes = await readJsonResource<readonly RecipeCatalogEntry[]>(client, "sg://recipes");
    const runtime = await readJsonResource<Record<string, unknown>>(client, "sg://runtime");
    const playbooks = await readJsonResource<readonly Readonly<{ name: string; directTools: readonly string[] }>[]>(client, "sg://playbooks");
    const pulseRecipe = recipes.find((recipe) => recipe.name === "Pulse Overview");

    if (pulseRecipe === undefined) {
      throw new Error("Pulse Overview recipe was not found.");
    }

    console.log("connected to Swee SG");
    console.log(`runtime: ${String(runtime.schemaVersion ?? "unknown")}`);
    console.log(`recipes: ${recipes.map((recipe) => recipe.name).join(", ")}`);
    console.log(`playbooks: ${playbooks.map((playbook) => playbook.name).join(", ")}`);
    console.log(`Pulse entrypoint: ${pulseRecipe.preferredEntrypoint.tool}`);

    const pulse = await callToolPayload<PulseToolPayload>(client, "swee_pulse_snapshot", {
      focus: "all",
      area: "Bedok",
    });
    const watchCount = pulse.snapshot.signals.filter((signal) => signal.severity === "watch").length;
    const disruptedCount = pulse.snapshot.signals.filter((signal) => signal.severity === "disrupted").length;
    console.log("\nPulse snapshot");
    console.log(`generatedAt: ${pulse.snapshot.generatedAt}`);
    console.log(`signals: ${pulse.snapshot.signals.length} (${disruptedCount} disrupted, ${watchCount} watch)`);
    console.log(`sources: ${pulse.snapshot.sourceHealth.map((source) => `${source.sourceTool}:${source.status}`).join(", ")}`);
    console.log(`gaps: ${pulse.snapshot.gaps.length}`);

    const shield = await callToolPayload<ShieldScanPayload>(client, "swee_shield_scan_tools", {});
    console.log("\nShield scan");
    console.log(`scanned tools: ${shield.scannedTools}`);
    console.log(`findings: ${shield.findings.length}`);
  } finally {
    await client.close();
  }
};

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
