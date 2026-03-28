#!/usr/bin/env node
// generates OpenAPI JSON from the built tool definitions
// usage: node scripts/generate-openapi.mjs > openapi.json
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { ZodFirstPartyTypeKind } from "zod";

const root = resolve(import.meta.dirname, "..");
const pkgJson = JSON.parse(readFileSync(resolve(root, "packages/mcp-server/package.json"), "utf8"));

const loadToolDefinitions = async () => {
  try {
    const moduleUrl = pathToFileURL(resolve(root, "packages/mcp-server/dist/tools/tool-set.js")).href;
    return (await import(moduleUrl)).ALL_TOOL_DEFINITIONS;
  } catch (error) {
    throw new Error(
      `Unable to load built tool definitions. Run "npm run build" first. ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
};

const unwrapSchema = (schema) => {
  let current = schema;
  let nullable = false;

  while (true) {
    const typeName = current?._def?.typeName;
    if (typeName === ZodFirstPartyTypeKind.ZodOptional || typeName === ZodFirstPartyTypeKind.ZodDefault) {
      current = current._def.innerType;
      continue;
    }
    if (typeName === ZodFirstPartyTypeKind.ZodNullable) {
      nullable = true;
      current = current._def.innerType;
      continue;
    }
    if (typeName === ZodFirstPartyTypeKind.ZodEffects) {
      current = current._def.schema;
      continue;
    }
    return { schema: current, nullable };
  }
};

const withNullable = (schema, nullable) => {
  return nullable ? { ...schema, nullable: true } : schema;
};

const zodFieldToOpenApi = (inputSchema) => {
  const { schema, nullable } = unwrapSchema(inputSchema);
  const typeName = schema?._def?.typeName;

  switch (typeName) {
    case ZodFirstPartyTypeKind.ZodString:
      return withNullable({ type: "string" }, nullable);
    case ZodFirstPartyTypeKind.ZodNumber: {
      const checks = Array.isArray(schema._def.checks) ? schema._def.checks : [];
      const isInteger = checks.some((check) => check.kind === "int");
      return withNullable({ type: isInteger ? "integer" : "number" }, nullable);
    }
    case ZodFirstPartyTypeKind.ZodBoolean:
      return withNullable({ type: "boolean" }, nullable);
    case ZodFirstPartyTypeKind.ZodEnum:
      return withNullable({ type: "string", enum: [...schema._def.values] }, nullable);
    case ZodFirstPartyTypeKind.ZodLiteral: {
      const literalValue = schema._def.value;
      return withNullable({
        type: typeof literalValue,
        enum: [literalValue],
      }, nullable);
    }
    case ZodFirstPartyTypeKind.ZodArray:
      return withNullable({
        type: "array",
        items: zodFieldToOpenApi(schema._def.type),
      }, nullable);
    case ZodFirstPartyTypeKind.ZodObject: {
      const shape = schema.shape;
      const properties = {};
      const required = [];
      for (const [key, value] of Object.entries(shape)) {
        properties[key] = zodFieldToOpenApi(value);
        if (!value.isOptional()) {
          required.push(key);
        }
      }
      return withNullable({
        type: "object",
        properties,
        ...(required.length === 0 ? {} : { required }),
      }, nullable);
    }
    default:
      return withNullable({}, nullable);
  }
};

const toRequestSchema = (shape) => {
  const properties = {};
  const required = [];

  for (const [key, value] of Object.entries(shape)) {
    properties[key] = zodFieldToOpenApi(value);
    if (!value.isOptional()) {
      required.push(key);
    }
  }

  return {
    type: "object",
    properties,
    ...(required.length === 0 ? {} : { required }),
    additionalProperties: false,
  };
};

const buildToolPath = (definition) => ({
  post: {
    summary: definition.description,
    tags: [definition.surface],
    requestBody: {
      required: false,
      content: {
        "application/json": {
          schema: toRequestSchema(definition.inputSchema),
        },
      },
    },
    responses: {
      200: {
        description: "Tool result",
        content: {
          "application/json": {
            schema: { type: "object" },
          },
        },
      },
      400: { description: "Tool error" },
      500: { description: "Server error" },
    },
  },
});

const toolDefinitions = await loadToolDefinitions();

const toolPaths = Object.fromEntries(
  [...toolDefinitions]
    .sort((left, right) => left.name.localeCompare(right.name))
    .map((definition) => [`/api/v1/${definition.name}`, buildToolPath(definition)]),
);

const spec = {
  openapi: "3.1.0",
  info: {
    title: "sg-apis-mcp REST Gateway",
    version: pkgJson.version,
    description: "REST interface for Singapore public data tools. Each tool is exposed as a POST endpoint.",
  },
  servers: [{ url: "http://localhost:3000", description: "Local REST gateway" }],
  paths: {
    "/api/v1/tools": {
      get: {
        summary: "List all available tools",
        responses: {
          200: {
            description: "Array of tool names and descriptions",
            content: {
              "application/json": {
                schema: {
                  type: "array",
                  items: {
                    type: "object",
                    properties: {
                      name: { type: "string" },
                      description: { type: "string" },
                    },
                  },
                },
              },
            },
          },
        },
      },
    },
    "/api/v1/health": {
      get: {
        summary: "Health check",
        responses: {
          200: {
            description: "Gateway health status",
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: {
                    status: { type: "string" },
                    tools: { type: "integer" },
                  },
                },
              },
            },
          },
        },
      },
    },
    ...toolPaths,
  },
};

process.stdout.write(`${JSON.stringify(spec, null, 2)}\n`);
