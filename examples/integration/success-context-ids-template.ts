import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const currentDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(currentDir, "..", "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const main = async () => {
  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: "error",
      SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS: "1",
    },
  });
  const client = new Client({ name: "success-context-ids-template", version: "0.1.0" });
  await client.connect(transport);

  try {
    const result = await client.callTool({
      name: "sg_config_get",
      arguments: {},
    });

    if (!("structuredContent" in result) || result.structuredContent === undefined || result.structuredContent === null) {
      throw new Error("sg_config_get did not return structuredContent.");
    }

    const structured = result.structuredContent as Record<string, unknown>;
    const contextIds = structured["contextIds"] as Record<string, unknown> | undefined;
    if (contextIds === undefined || contextIds === null) {
      throw new Error("sg_config_get did not include structuredContent.contextIds with SG_APIS_INCLUDE_SUCCESS_CONTEXT_IDS=1.");
    }

    const traceId = contextIds["traceId"];
    const requestId = contextIds["requestId"];
    if (typeof traceId !== "string" || !UUID_PATTERN.test(traceId)) {
      throw new Error("structuredContent.contextIds.traceId is missing or not a UUID.");
    }
    if (typeof requestId !== "string" || !UUID_PATTERN.test(requestId)) {
      throw new Error("structuredContent.contextIds.requestId is missing or not a UUID.");
    }

    console.log(`[ok] success context IDs attached (traceId=${traceId}, requestId=${requestId})`);
  } finally {
    await client.close();
  }
};

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
