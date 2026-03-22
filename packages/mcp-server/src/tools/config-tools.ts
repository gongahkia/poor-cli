import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, ConfigSetSchema, loadConfig, formatResponse } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { registerTool } from "./registry.js";

export const registerConfigTools = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_config_get",
    description: "Show current sg-apis-mcp configuration including cache TTLs, rate limits, and timeouts.",
    inputSchema: {},
    handler: async (_input: unknown): Promise<ToolResult> => {
      const config = loadConfig();
      const text = formatResponse(config as unknown as Record<string, unknown>, "json");
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_config_set",
    description: "Update sg-apis-mcp configuration. Changes persist in ~/.sg-apis/config.json.",
    inputSchema: ConfigSetSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { key, value } = validateInput(ConfigSetSchema, input);
      const configDir = join(homedir(), ".sg-apis");
      const configPath = join(configDir, "config.json");
      mkdirSync(configDir, { recursive: true });

      let existing: Record<string, unknown> = {};
      try {
        const { readFileSync } = await import("node:fs");
        existing = JSON.parse(readFileSync(configPath, "utf-8")) as Record<string, unknown>;
      } catch { /* no existing config */ }

      const parts = key.split(".");
      let current: Record<string, unknown> = existing;
      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i]!;
        if (current[part] === undefined || typeof current[part] !== "object") {
          current[part] = {};
        }
        current = current[part] as Record<string, unknown>;
      }
      const lastPart = parts[parts.length - 1]!;
      const numVal = Number(value);
      current[lastPart] = isNaN(numVal) ? value : numVal;

      writeFileSync(configPath, JSON.stringify(existing, null, 2));
      return { content: [{ type: "text", text: `Config updated: ${key} = ${value}` }] };
    },
  });
};
