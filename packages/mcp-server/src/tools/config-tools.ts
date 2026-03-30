import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import {
  validateInput,
  ConfigSetSchema,
  ValidationError,
  loadConfig,
  formatResponse,
  parseMutableConfigValue,
  resetConfigCache,
  resetRateLimiters,
} from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const configToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_config_get",
    description: "Show current sg-apis-mcp configuration including cache TTLs, rate limits, and timeouts.",
    surface: "operational",
    inputSchema: {},
    handler: async (_input: unknown): Promise<ToolResult> => {
      const config = loadConfig();
      const text = formatResponse(config as unknown as Record<string, unknown>, "json");
      return {
        content: [{ type: "text", text }],
        structuredContent: {
          record: config as unknown as Record<string, unknown>,
        },
      };
    },
  },

  {
    name: "sg_config_set",
    description: "Update sg-apis-mcp configuration. Changes persist in ~/.sg-apis/config.json.",
    surface: "operational",
    inputSchema: ConfigSetSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { key, value } = validateInput(ConfigSetSchema, input);
      let parsedValue: string | number;
      try {
        parsedValue = parseMutableConfigValue(key, value);
      } catch (error) {
        throw new ValidationError(
          error instanceof Error ? error.message : String(error),
          [],
        );
      }
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
      current[lastPart] = parsedValue;

      writeFileSync(configPath, JSON.stringify(existing, null, 2));
      resetConfigCache();
      resetRateLimiters();
      return { content: [{ type: "text", text: `Config updated: ${key} = ${value}` }] };
    },
  },
];
