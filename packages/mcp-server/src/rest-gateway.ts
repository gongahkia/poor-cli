import { randomUUID } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { createLogger } from "@swee-sg/shared";
import type { ToolResult } from "@swee-sg/shared";
import { buildShieldToolMetadata } from "./shield/policy.js";
import { invokeWithShield } from "./shield/enforcement.js";
import { loadShieldPolicy } from "./shield/policy.js";
import { shieldAuditStore } from "./shield/audit-store.js";
import { ALL_TOOL_DEFINITIONS } from "./tools/tool-set.js";
import { isToolEnabled } from "./tools/tool-metadata.js";
import type { RegisteredToolDefinition } from "./tools/tool-definition.js";
import { resolveEnabledToolsets } from "./tools/toolset-profiles.js";

const logger = createLogger("rest-gateway");
const PORT = Number(process.env["PORT"] ?? 3000);
const MAX_BODY_BYTES = 1024 * 1024;
const DEFAULT_ALLOWED_ORIGINS = new Set([
  "http://localhost:5173",
  "http://127.0.0.1:5173",
  "http://localhost:5174",
  "http://127.0.0.1:5174",
  "http://localhost:5175",
  "http://127.0.0.1:5175",
]);

const configuredOrigins = (process.env["SWEE_WEB_ORIGIN_ALLOWLIST"] ?? process.env["DUDE_WEB_ORIGIN_ALLOWLIST"] ?? "")
  .split(",")
  .map((value) => value.trim())
  .filter((value) => value.length > 0);
const allowedOrigins = configuredOrigins.length === 0 ? DEFAULT_ALLOWED_ORIGINS : new Set(configuredOrigins);

const enabledToolsets = resolveEnabledToolsets({
  transportMode: "http",
  configuredToolsets: process.env["SWEE_TOOLSETS"] ?? process.env["SG_APIS_TOOLSETS"],
  configuredProfile: process.env["SWEE_TOOL_PROFILE"] ?? process.env["SG_APIS_TOOL_PROFILE"],
});
const enabledTools = ALL_TOOL_DEFINITIONS.filter((tool) => isToolEnabled(tool, enabledToolsets));
const toolMap = new Map<string, RegisteredToolDefinition>();
for (const tool of enabledTools) {
  toolMap.set(tool.name, tool);
}

const sendJson = (res: ServerResponse, status: number, payload: unknown): void => {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(payload));
};

const readBody = async (req: IncomingMessage): Promise<string> => {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.byteLength;
    if (size > MAX_BODY_BYTES) {
      throw new Error(`Request body must be ${MAX_BODY_BYTES} bytes or smaller.`);
    }
    chunks.push(buffer);
  }
  return Buffer.concat(chunks).toString("utf8");
};

const getOrigin = (req: IncomingMessage): string | undefined => {
  const origin = req.headers.origin;
  return typeof origin === "string" && origin !== "" ? origin : undefined;
};

const applyCors = (req: IncomingMessage, res: ServerResponse): boolean => {
  const origin = getOrigin(req);
  if (origin === undefined) return true;
  if (!allowedOrigins.has(origin)) return false;
  res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", req.headers["access-control-request-headers"] ?? "Content-Type");
  res.setHeader("Vary", "Origin");
  return true;
};

const parseJsonBody = async (req: IncomingMessage): Promise<Readonly<Record<string, unknown>>> => {
  const body = await readBody(req);
  if (body.trim() === "") return {};
  const parsed = JSON.parse(body) as unknown;
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Request body must be a JSON object.");
  }
  return parsed as Readonly<Record<string, unknown>>;
};

const toolEnvelope = (result: ToolResult): Readonly<Record<string, unknown>> => ({
  content: result.content,
  ...(result.structuredContent === undefined ? {} : { data: result.structuredContent }),
  ...(result._meta === undefined ? {} : { _meta: result._meta }),
});

const callTool = async (
  toolName: string,
  input: Readonly<Record<string, unknown>>,
  requestId: string,
): Promise<ToolResult> => {
  const tool = toolMap.get(toolName) ?? toolMap.get(`sg_${toolName}`) ?? toolMap.get(`swee_${toolName}`);
  if (tool === undefined) {
    return {
      isError: true,
      content: [{ type: "text", text: `Tool not found or not enabled: ${toolName}` }],
      structuredContent: {
        error: {
          source: "rest-gateway",
          tool: toolName,
          code: "TOOL_NOT_FOUND",
          retryable: false,
          message: `Tool not found or not enabled: ${toolName}`,
        },
      },
    };
  }
  return invokeWithShield({
    toolName: tool.name,
    input,
    requestId,
    metadata: buildShieldToolMetadata(tool),
    handler: tool.handler,
  });
};

const getPulseInput = (url: URL): Readonly<Record<string, unknown>> => ({
  ...(url.searchParams.get("focus") === null ? {} : { focus: url.searchParams.get("focus") ?? undefined }),
  ...(url.searchParams.get("area") === null ? {} : { area: url.searchParams.get("area") ?? undefined }),
  ...(url.searchParams.get("region") === null ? {} : { region: url.searchParams.get("region") ?? undefined }),
  ...(url.searchParams.get("stationId") === null ? {} : { stationId: url.searchParams.get("stationId") ?? undefined }),
});

const server = createServer(async (req, res) => {
  const requestId = randomUUID();
  const started = Date.now();
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);

  if (!applyCors(req, res)) {
    sendJson(res, 403, { error: { code: "CORS_FORBIDDEN", message: "Origin is not allowed." } });
    return;
  }
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  try {
    if (req.method === "GET" && url.pathname === "/api/v1/tools") {
      sendJson(res, 200, enabledTools.map((tool) => ({
        name: tool.name,
        title: tool.title,
        description: tool.description,
        toolsets: tool.toolsets,
        shield: buildShieldToolMetadata(tool),
      })));
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/v1/health") {
      sendJson(res, 200, {
        status: "ready",
        product: "Swee SG",
        toolCount: enabledTools.length,
        toolsets: [...enabledToolsets],
        shieldMode: loadShieldPolicy().mode,
        observedAt: new Date().toISOString(),
      });
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/v1/shield/policy") {
      sendJson(res, 200, loadShieldPolicy());
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/v1/shield/audit") {
      const limit = Number(url.searchParams.get("limit") ?? "50");
      sendJson(res, 200, { records: shieldAuditStore.recent(Number.isFinite(limit) ? limit : 50) });
      return;
    }

    if (req.method === "GET" && url.pathname.startsWith("/api/v1/shield/audit/")) {
      const id = decodeURIComponent(url.pathname.slice("/api/v1/shield/audit/".length));
      const record = shieldAuditStore.get(id);
      sendJson(res, record === null ? 404 : 200, record === null ? { error: "audit record not found" } : { record });
      return;
    }

    if (req.method === "POST" && url.pathname === "/api/v1/shield/evaluate") {
      const result = await callTool("swee_shield_evaluate", await parseJsonBody(req), requestId);
      sendJson(res, result.isError === true ? 400 : 200, toolEnvelope(result));
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/v1/pulse/snapshot") {
      const result = await callTool("swee_pulse_snapshot", getPulseInput(url), requestId);
      sendJson(res, result.isError === true ? 400 : 200, toolEnvelope(result));
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/v1/pulse/mobility") {
      const result = await callTool("swee_pulse_mobility", {}, requestId);
      sendJson(res, result.isError === true ? 400 : 200, toolEnvelope(result));
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/v1/pulse/weather") {
      const result = await callTool("swee_pulse_weather", getPulseInput(url), requestId);
      sendJson(res, result.isError === true ? 400 : 200, toolEnvelope(result));
      return;
    }

    if (req.method === "POST" && url.pathname === "/api/v1/pulse/explain") {
      const result = await callTool("swee_pulse_explain", await parseJsonBody(req), requestId);
      sendJson(res, result.isError === true ? 400 : 200, toolEnvelope(result));
      return;
    }

    if (req.method === "POST" && url.pathname.startsWith("/api/v1/")) {
      const toolName = url.pathname.slice("/api/v1/".length).replace(/-/g, "_");
      const result = await callTool(toolName, await parseJsonBody(req), requestId);
      sendJson(res, result.isError === true ? 400 : 200, toolEnvelope(result));
      return;
    }

    sendJson(res, 404, {
      error: "not found",
      hint: "GET /api/v1/tools, GET /api/v1/pulse/snapshot, or POST /api/v1/<tool-name>",
    });
  } catch (error) {
    logger.error("REST gateway request failed", {
      requestId,
      route: url.pathname,
      durationMs: Date.now() - started,
      error,
    });
    sendJson(res, 500, {
      error: {
        code: "REST_GATEWAY_ERROR",
        message: error instanceof Error ? error.message : String(error),
      },
    });
  }
});

server.listen(PORT, () => {
  console.log(`Swee SG REST gateway listening on http://localhost:${PORT}`);
  console.log(`tools: ${enabledTools.length}/${ALL_TOOL_DEFINITIONS.length} (toolsets: ${[...enabledToolsets].join(",")})`);
  console.log(`try: curl http://localhost:${PORT}/api/v1/pulse/snapshot`);
});
