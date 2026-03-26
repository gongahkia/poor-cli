// basic MCP client integration example for sg-apis-mcp
// run: npx tsx examples/integration/basic-client.ts
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { spawn } from "node:child_process";

const main = async () => {
  const serverProcess = spawn("node", ["packages/mcp-server/dist/index.js"], {
    stdio: ["pipe", "pipe", "inherit"],
  });
  const transport = new StdioClientTransport({
    command: "node",
    args: ["packages/mcp-server/dist/index.js"],
  });
  const client = new Client({ name: "example-client", version: "0.1.0" });
  await client.connect(transport);
  console.log("connected to sg-apis-mcp");

  // 1. read discovery resources
  const recipes = await client.readResource({ uri: "sg://recipes" });
  console.log("recipes:", recipes.contents[0]?.text?.slice(0, 200) + "...");

  // 2. call sg_query with a sample prompt
  const queryResult = await client.callTool({
    name: "sg_query",
    arguments: { query: "property brief for Bedok", format: "json" },
  });
  const queryText = (queryResult.content as { type: string; text: string }[])[0]?.text ?? "";
  const parsed = JSON.parse(queryText);

  // 3. handle blocked/unsupported/completed
  if (parsed.status === "blocked") {
    console.log("query blocked:", parsed.blockers);
    console.log("suggestion: provide the missing parameters and retry");
  } else if (parsed.status === "unsupported") {
    console.log("query unsupported:", parsed.reason);
    console.log("fallback: use a direct sg_* tool instead");
  } else {
    console.log("query completed:", parsed.workflow);
    console.log("steps:", parsed.steps?.length ?? 0);
  }

  // 4. fallback to direct tool call
  console.log("\n--- direct tool fallback ---");
  const directResult = await client.callTool({
    name: "sg_nea_forecast_2hr",
    arguments: { area: "Bedok" },
  });
  const forecastText = (directResult.content as { type: string; text: string }[])[0]?.text ?? "";
  console.log("forecast:", forecastText.slice(0, 300));

  // 5. health check
  const health = await client.callTool({ name: "sg_health_check", arguments: {} });
  console.log("\nhealth:", (health.content as { type: string; text: string }[])[0]?.text?.slice(0, 200));

  await client.close();
  serverProcess.kill();
  console.log("\ndone");
};

main().catch((err) => {
  console.error("error:", err);
  process.exit(1);
});
