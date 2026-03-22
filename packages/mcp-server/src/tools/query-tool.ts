import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, QuerySchema, ApiError } from "@sg-apis/shared";
import type { ToolResult, OutputFormat } from "@sg-apis/shared";
import { classifyIntent, resolveTools } from "../router/classifier.js";
import { planQuery } from "../router/planner.js";
import { aggregateResults, formatAggregated } from "../router/aggregator.js";
import type { StepResult } from "../router/aggregator.js";
import { ConversationContext } from "../router/context.js";
import { registerTool } from "./registry.js";

const context = new ConversationContext();

export const registerQueryTool = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_query",
    description:
      "Natural language query interface for Singapore government data. Automatically determines which APIs to query and how to combine results.",
    inputSchema: QuerySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { query, format } = validateInput(QuerySchema, input);
      const fmt = (format ?? "markdown") as OutputFormat;

      const intent = classifyIntent(query);
      const plan = planQuery(query);

      // Execute plan steps
      const results: StepResult[] = [];
      for (const step of plan.steps) {
        try {
          const tools = resolveTools(intent);
          const toolData = tools.length > 0 ? tools[0] : null;
          results.push({
            tool: step.tool,
            data: toolData?.input ?? {},
            cached: false,
          });
        } catch (error) {
          results.push({
            tool: step.tool,
            data: null,
            cached: false,
            error: new ApiError({
              apiName: step.tool,
              statusCode: 500,
              message: error instanceof Error ? error.message : String(error),
              retryable: false,
            }),
          });
        }
      }

      const aggregated = aggregateResults(results);
      context.update(query, plan, intent.extractedParams);

      const text = formatAggregated(aggregated, fmt);
      return { content: [{ type: "text", text }] };
    },
  });
};
