// Truthful TypeScript MCP client example for Dude MCP.
// Run after `npm run build`:
//   npx tsx examples/integration/basic-client.ts
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

type TextContent = Readonly<{
  type?: string;
  text?: string;
}>;

type ResourceTextContent = Readonly<{
  text?: string;
}>;

type RecipeCatalogEntry = Readonly<{
  name: string;
  prompt: string;
  goal: string;
  fallbackTools: readonly string[];
  preferredEntrypoint: Readonly<{
    tool: string;
    input: Readonly<Record<string, unknown>>;
  }>;
}>;

type QueryBlocker = Readonly<{
  field: string;
  directTool: string;
  suggestedPrompt: string;
}>;

type QueryOutcome = Readonly<{
  status?: "planned" | "completed" | "blocked" | "unsupported" | "failed";
  workflow?: string;
  reason?: string;
  suggestion?: string;
  toolsUsed?: readonly string[];
  blockers?: readonly QueryBlocker[];
  routingExplanation?: string;
  failedStep?: Readonly<{
    tool?: string;
  }> | null;
}>;

type DirectoryPayload = Readonly<{
  records?: readonly Readonly<Record<string, unknown>>[];
}>;

type RuntimeCatalog = Readonly<{
  releaseReadiness?: Readonly<{
    blockingCommands?: readonly string[];
  }>;
  queryStatusContract?: readonly Readonly<{
    status: string;
    isError: boolean;
  }>[];
}>;

type PlaybookCatalogEntry = Readonly<{
  id?: string;
  name: string;
  persona: string;
  directTools: readonly string[];
}>;

type BenchmarkCatalog = Readonly<{
  workflowProfiles?: readonly Readonly<{
    workflow: string;
    primaryCacheTier: string;
  }>[];
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

const readJsonResource = async <T>(
  client: Client,
  uri: string,
): Promise<T> => {
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

const callQuery = async (
  client: Client,
  query: string,
): Promise<QueryOutcome> => {
  const result = await client.callTool({
    name: "sg_query",
    arguments: {
      query,
      mode: "execute",
      format: "json",
    },
  });

  if ("structuredContent" in result && typeof result.structuredContent === "object" && result.structuredContent !== null) {
    return result.structuredContent as QueryOutcome;
  }

  return JSON.parse(getText(result.content as readonly TextContent[])) as QueryOutcome;
};

const logQueryOutcome = (label: string, outcome: QueryOutcome): void => {
  console.log(`\n${label}`);
  console.log(`status: ${outcome.status ?? "unknown"}`);
  if (outcome.workflow !== undefined) {
    console.log(`workflow: ${outcome.workflow}`);
  }
  if (Array.isArray(outcome.toolsUsed) && outcome.toolsUsed.length > 0) {
    console.log(`tools: ${outcome.toolsUsed.join(", ")}`);
  }
  if (typeof outcome.reason === "string") {
    console.log(`reason: ${outcome.reason}`);
  }
  if (typeof outcome.suggestion === "string") {
    console.log(`suggestion: ${outcome.suggestion}`);
  }
  if (Array.isArray(outcome.blockers) && outcome.blockers.length > 0) {
    const firstBlocker = outcome.blockers[0];
    console.log(`first blocker: ${firstBlocker.field} -> ${firstBlocker.directTool}`);
    console.log(`recovery prompt: ${firstBlocker.suggestedPrompt}`);
  }
  if (typeof outcome.routingExplanation === "string") {
    console.log(`routing: ${outcome.routingExplanation}`);
  }
  if (outcome.failedStep?.tool !== undefined) {
    console.log(`failed step: ${outcome.failedStep.tool}`);
  }
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
  const client = new Client({ name: "basic-client-example", version: "0.1.0" });

  await client.connect(transport);

  try {
    const recipes = await readJsonResource<readonly RecipeCatalogEntry[]>(client, "sg://recipes");
    const runtime = await readJsonResource<RuntimeCatalog>(client, "sg://runtime");
    const playbooks = await readJsonResource<readonly PlaybookCatalogEntry[]>(client, "sg://playbooks");
    const benchmarks = await readJsonResource<BenchmarkCatalog>(client, "sg://benchmarks");
    const health = await callToolPayload<{ records: readonly Readonly<Record<string, unknown>>[] }>(client, "sg_health_check", {});
    const recipeCache = new Map(recipes.map((recipe) => [recipe.name, recipe]));
    const businessRecipe = recipeCache.get("Business Due Diligence");
    const architectureRecipe = recipeCache.get("Architecture Firm Diligence");
    const cddPlaybook = playbooks.find((playbook) => playbook.id === "business_opportunity_scan");

    if (businessRecipe === undefined || architectureRecipe === undefined || cddPlaybook === undefined) {
      throw new Error("Expected recipe catalog entries were not found.");
    }

    console.log(`connected to Dude MCP`);
    console.log(`cached ${recipeCache.size} recipes from sg://recipes`);
    console.log(`cached ${playbooks.length} playbooks from sg://playbooks`);
    console.log(`runtime statuses: ${(runtime.queryStatusContract ?? []).map((entry) => `${entry.status}:${entry.isError ? "error" : "ok"}`).join(", ")}`);
    console.log(`release gates: ${(runtime.releaseReadiness?.blockingCommands ?? []).join(", ")}`);
    console.log(`benchmark workflows: ${(benchmarks.workflowProfiles ?? []).map((profile) => `${profile.workflow}:${profile.primaryCacheTier}`).join(", ")}`);
    console.log(`health probes: ${(health.records ?? []).map((record) => `${record.api}:${record.reachable === true ? "up" : "down"}`).join(", ")}`);
    console.log(`business fallback tools: ${businessRecipe.fallbackTools.join(", ")}`);
    console.log(`architecture prompt shape: ${architectureRecipe.prompt}`);
    console.log(`CDD playbook direct tools: ${cddPlaybook.directTools.join(", ")}`);

    const supportedOutcome = await callQuery(
      client,
      "Architecture firm diligence for DP Architects",
    );
    logQueryOutcome("covered prompt via sg_query", supportedOutcome);

    const blockedOutcome = await callQuery(client, "Run business diligence");
    logQueryOutcome("blocked prompt", blockedOutcome);

    const unsupportedOutcome = await callQuery(client, "Compare GDP and CPI in Singapore");
    logQueryOutcome("unsupported prompt", unsupportedOutcome);

    const failedOutcome: QueryOutcome = {
      status: "failed",
      workflow: "business_dossier",
      reason: "Synthetic example for failed-state UI handling.",
      failedStep: { tool: "sg_business_dossier" },
    };
    logQueryOutcome("failed prompt", failedOutcome);

    const directLookup = await callToolPayload<DirectoryPayload>(client, "sg_acra_entities", {
      entityName: "DP ARCHITECTS PTE LTD",
      format: "json",
    });
    console.log("\nexact-parameter direct lookup");
    console.log(`tool: sg_acra_entities`);
    console.log(`records: ${directLookup.records?.length ?? 0}`);
  } finally {
    await client.close();
  }
};

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
