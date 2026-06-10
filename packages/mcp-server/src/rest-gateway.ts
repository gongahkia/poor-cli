#!/usr/bin/env node
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { randomUUID } from "node:crypto";
import { ApiError, createLogger } from "@swee-sg/shared";
import { getGatewayMetricsSnapshot, recordGatewayRequest } from "./gateway/metrics.js";
import { getGatewayHealthPayload } from "./gateway/readiness.js";
import {
  buildRateLimitResponse,
  checkTrafficLimit,
  getClientId,
  getTrafficPolicy,
} from "./gateway/traffic-control.js";
import { getShieldAuditStore } from "./shield/audit-store.js";
import { getShieldApprovalStore, type ShieldApprovalStatus } from "./shield/approval-store.js";
import { invokeShieldedTool } from "./shield/enforcement.js";
import { scanToolCatalogForPoisoning } from "./shield/scanner.js";
import { ALL_TOOL_DEFINITIONS } from "./tools/tool-set.js";
import { isToolEnabled } from "./tools/tool-metadata.js";
import { resolveEnabledToolsets } from "./tools/toolset-profiles.js";

const PORT = Number(process.env["PORT"] ?? 3000);
const DEFAULT_DEV_WEB_ORIGIN_ALLOWLIST = [
  "http://localhost:5173",
  "http://127.0.0.1:5173",
  "http://localhost:5174",
  "http://127.0.0.1:5174",
  "http://localhost:5175",
  "http://127.0.0.1:5175",
].join(",");

const gatewayStartedAt = new Date();
const logger = createLogger("rest-gateway");
const configuredToolsets = process.env["SG_APIS_TOOLSETS"];
const configuredProfile = process.env["SG_APIS_TOOL_PROFILE"];
const enabledToolsets = resolveEnabledToolsets({
  transportMode: "http",
  ...(configuredToolsets === undefined ? {} : { configuredToolsets }),
  ...(configuredProfile === undefined ? {} : { configuredProfile }),
});
const enabledTools = ALL_TOOL_DEFINITIONS.filter((tool) => isToolEnabled(tool, enabledToolsets));
const toolMap = new Map(enabledTools.map((tool) => [tool.name, tool]));
const allToolMap = new Map(ALL_TOOL_DEFINITIONS.map((tool) => [tool.name, tool]));
const allowedCorsOrigins = new Set(
  `${DEFAULT_DEV_WEB_ORIGIN_ALLOWLIST},${process.env["SWEE_WEB_ORIGIN_ALLOWLIST"] ?? ""}`
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
);

logger.info("gateway started", {
  toolsets: [...enabledToolsets],
  tools: enabledTools.length,
  total: ALL_TOOL_DEFINITIONS.length,
  corsOrigins: [...allowedCorsOrigins],
});

class RequestBodyTooLargeError extends Error {
  readonly statusCode = 413;

  constructor(readonly maxBytes: number) {
    super(`Request body exceeds ${maxBytes} bytes.`);
    this.name = "RequestBodyTooLargeError";
  }
}

const getOrigin = (req: IncomingMessage): string | undefined => {
  const origin = req.headers.origin;
  return typeof origin === "string" && origin.trim() !== "" ? origin : undefined;
};

const applyCorsHeaders = (req: IncomingMessage, res: ServerResponse): boolean => {
  const origin = getOrigin(req);
  if (origin === undefined) return true;
  if (!allowedCorsOrigins.has(origin)) return false;
  res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type,Authorization");
  res.setHeader("Vary", "Origin");
  return true;
};

const readBody = (req: IncomingMessage, maxBytes: number): Promise<string> =>
  new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let totalBytes = 0;
    let rejected = false;
    req.on("data", (chunk: Buffer) => {
      if (rejected) return;
      totalBytes += chunk.byteLength;
      if (totalBytes > maxBytes) {
        rejected = true;
        reject(new RequestBodyTooLargeError(maxBytes));
        req.resume();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
    req.on("error", reject);
  });

const sendJson = (res: ServerResponse, status: number, body: unknown): void => {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
};

const parseJsonBody = async (req: IncomingMessage, maxBytes: number): Promise<unknown> => {
  const body = await readBody(req, maxBytes);
  return body.trim() === "" ? {} : JSON.parse(body);
};

const pulseInputFromUrl = (url: URL): Record<string, string> => {
  const input: Record<string, string> = {};
  for (const key of ["area", "region", "stationId", "focus"]) {
    const value = url.searchParams.get(key)?.trim();
    if (value !== undefined && value !== "") input[key] = value;
  }
  return input;
};

const parseApprovalStatus = (value: string | null): ShieldApprovalStatus | undefined => {
  if (value === "pending" || value === "approved" || value === "rejected" || value === "expired") return value;
  return undefined;
};

const invokeToolDefinition = async (params: {
  readonly tool: (typeof ALL_TOOL_DEFINITIONS)[number] | undefined;
  readonly input: unknown;
  readonly requestId: string;
  readonly traceId: string;
}) => {
  if (params.tool === undefined) return null;
  const result = await invokeShieldedTool(params.tool, params.input, {
    traceId: params.traceId,
    requestId: params.requestId,
  });
  return {
    status: result.isError === true ? 400 : 200,
    body: {
      content: result.content,
      data: result.structuredContent ?? {},
      shield: {
        auditId: result.shieldAudit.auditId,
        decision: result.shieldAudit.decision,
      },
    },
  };
};

const invokeTool = async (params: {
  readonly toolName: string;
  readonly input: unknown;
  readonly requestId: string;
  readonly traceId: string;
}) => {
  const tool = toolMap.get(params.toolName) ?? toolMap.get(`sg_${params.toolName}`);
  return invokeToolDefinition({ tool, input: params.input, requestId: params.requestId, traceId: params.traceId });
};

const server = createServer(async (req, res) => {
  const requestStartedAt = Date.now();
  const requestId = randomUUID();
  const traceId = randomUUID();
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const method = req.method ?? "UNKNOWN";
  const route = url.pathname;
  const requestLogger = logger.child({ requestId, traceId, method, route });
  const isApiRoute = route.startsWith("/api/v1/");
  const corsAllowed = isApiRoute ? applyCorsHeaders(req, res) : false;

  res.on("finish", () => {
    recordGatewayRequest({ method, route, status: res.statusCode, durationMs: Date.now() - requestStartedAt });
    requestLogger.info("request finished", { status: res.statusCode, durationMs: Date.now() - requestStartedAt });
  });

  if (method === "OPTIONS" && isApiRoute) {
    res.writeHead(corsAllowed ? 204 : 403);
    res.end();
    return;
  }

  const trafficPolicy = getTrafficPolicy(method, route);
  const trafficLimit = checkTrafficLimit({ clientId: getClientId(req), policy: trafficPolicy });
  res.setHeader("X-RateLimit-Limit", String(trafficPolicy.maxRequests));
  res.setHeader("X-RateLimit-Remaining", String(trafficLimit.remaining));
  res.setHeader("X-RateLimit-Reset", String(Math.ceil(trafficLimit.resetAt / 1000)));
  if (!trafficLimit.allowed) {
    res.setHeader("Retry-After", String(trafficLimit.retryAfterSeconds));
    sendJson(res, 429, buildRateLimitResponse(trafficPolicy, trafficLimit));
    return;
  }

  try {
    if (method === "GET" && route === "/api/v1/tools") {
      sendJson(res, 200, enabledTools.map((tool) => ({ name: tool.name, description: tool.description, toolsets: tool.toolsets })));
      return;
    }

    if (method === "GET" && route === "/api/v1/health") {
      const health = await getGatewayHealthPayload({
        gateway: {
          status: "ready",
          message: "Swee SG REST gateway is accepting local requests.",
          observedAt: new Date().toISOString(),
          details: { toolsets: [...enabledToolsets].join(",") },
        },
        toolCount: enabledTools.length,
        startedAt: gatewayStartedAt,
      });
      sendJson(res, 200, health);
      return;
    }

    if (method === "GET" && route === "/api/v1/metrics") {
      sendJson(res, 200, getGatewayMetricsSnapshot({ startedAt: gatewayStartedAt }));
      return;
    }

    if (method === "GET" && route === "/api/v1/shield/audits") {
      const traceFilter = url.searchParams.get("traceId") ?? undefined;
      const requestFilter = url.searchParams.get("requestId") ?? undefined;
      const toolFilter = url.searchParams.get("toolName") ?? undefined;
      sendJson(res, 200, {
        records: getShieldAuditStore().query({
          ...(traceFilter === undefined ? {} : { traceId: traceFilter }),
          ...(requestFilter === undefined ? {} : { requestId: requestFilter }),
          ...(toolFilter === undefined ? {} : { toolName: toolFilter }),
          limit: Number(url.searchParams.get("limit") ?? 25),
        }),
      });
      return;
    }

    if (method === "GET" && route.startsWith("/api/v1/shield/audits/")) {
      const auditId = decodeURIComponent(route.slice("/api/v1/shield/audits/".length));
      const store = getShieldAuditStore();
      const record = store.get(auditId);
      sendJson(res, record === null ? 404 : 200, record === null ? { error: "audit not found" } : {
        record,
        replay: store.getReplay(auditId),
      });
      return;
    }

    if (method === "GET" && route === "/api/v1/shield/approvals") {
      const statusFilter = parseApprovalStatus(url.searchParams.get("status"));
      const toolFilter = url.searchParams.get("toolName") ?? undefined;
      sendJson(res, 200, {
        records: getShieldApprovalStore().list({
          ...(statusFilter === undefined ? {} : { status: statusFilter }),
          ...(toolFilter === undefined ? {} : { toolName: toolFilter }),
          limit: Number(url.searchParams.get("limit") ?? 25),
        }),
      });
      return;
    }

    if (method === "POST" && route.startsWith("/api/v1/shield/approvals/") && route.endsWith("/decide")) {
      const approvalId = decodeURIComponent(route.slice("/api/v1/shield/approvals/".length, -"/decide".length));
      const body = await parseJsonBody(req, trafficPolicy.maxBodyBytes);
      const payload = body !== null && typeof body === "object" ? body as Record<string, unknown> : {};
      const decision = payload["decision"];
      if (decision !== "approved" && decision !== "rejected") {
        sendJson(res, 400, { error: { code: "INVALID_APPROVAL_DECISION", message: "decision must be approved or rejected." } });
        return;
      }
      const reviewer = typeof payload["reviewer"] === "string" ? payload["reviewer"] : undefined;
      const comment = typeof payload["comment"] === "string" ? payload["comment"] : undefined;
      sendJson(res, 200, {
        record: getShieldApprovalStore().decide({
          approvalId,
          decision,
          ...(reviewer === undefined ? {} : { reviewer }),
          ...(comment === undefined ? {} : { comment }),
        }),
      });
      return;
    }

    if (method === "GET" && route.startsWith("/api/v1/shield/replay/")) {
      const auditId = decodeURIComponent(route.slice("/api/v1/shield/replay/".length));
      const replay = getShieldAuditStore().getReplay(auditId);
      sendJson(res, replay === null ? 404 : 200, replay ?? { error: "audit not found" });
      return;
    }

    if (method === "GET" && route === "/api/v1/shield/scan") {
      sendJson(res, 200, { findings: scanToolCatalogForPoisoning(enabledTools), scannedTools: enabledTools.length });
      return;
    }

    if (method === "POST" && route === "/api/v1/shield/policy/simulate") {
      const input = await parseJsonBody(req, trafficPolicy.maxBodyBytes);
      const invoked = await invokeToolDefinition({
        tool: allToolMap.get("swee_shield_policy_simulate"),
        input,
        requestId,
        traceId,
      });
      sendJson(res, invoked?.status ?? 404, invoked?.body ?? { error: "policy simulator is not available" });
      return;
    }

    if (method === "POST" && route === "/api/v1/shield/splunk/investigation-pack") {
      const body = await parseJsonBody(req, trafficPolicy.maxBodyBytes);
      const input = body !== null && typeof body === "object"
        ? { ...(body as Record<string, unknown>), mode: "mock" }
        : { mode: "mock" };
      const invoked = await invokeToolDefinition({
        tool: allToolMap.get("swee_shield_splunk_investigation_pack"),
        input,
        requestId,
        traceId,
      });
      sendJson(res, invoked?.status ?? 404, invoked?.body ?? { error: "Splunk investigation pack is not available" });
      return;
    }

    const pulseRouteTool = route === "/api/v1/pulse/snapshot"
      ? "swee_pulse_snapshot"
      : route === "/api/v1/pulse/mobility"
        ? "swee_pulse_mobility"
        : route === "/api/v1/pulse/weather"
          ? "swee_pulse_weather"
          : route === "/api/v1/pulse/explain"
            ? "swee_pulse_explain"
            : null;
    if (pulseRouteTool !== null && (method === "GET" || method === "POST")) {
      const input = method === "GET" ? pulseInputFromUrl(url) : await parseJsonBody(req, trafficPolicy.maxBodyBytes);
      const invoked = await invokeTool({ toolName: pulseRouteTool, input, requestId, traceId });
      sendJson(res, invoked?.status ?? 404, invoked?.body ?? { error: "pulse tool is not enabled" });
      return;
    }

    if (method === "POST" && route.startsWith("/api/v1/")) {
      const toolName = route.slice("/api/v1/".length).replace(/-/g, "_");
      const input = await parseJsonBody(req, trafficPolicy.maxBodyBytes);
      const invoked = await invokeTool({ toolName, input, requestId, traceId });
      if (invoked === null) {
        sendJson(res, 404, { error: `tool not found or not enabled: ${toolName}` });
        return;
      }
      sendJson(res, invoked.status, invoked.body);
      return;
    }

    sendJson(res, 404, {
      error: "not found",
      hint: "Use GET /api/v1/tools, GET /api/v1/pulse/snapshot, or POST /api/v1/<tool-name>.",
    });
  } catch (error) {
    if (error instanceof RequestBodyTooLargeError) {
      sendJson(res, error.statusCode, {
        error: { code: "REQUEST_BODY_TOO_LARGE", message: `Request body must be ${error.maxBytes} bytes or smaller.` },
      });
      return;
    }
    if (error instanceof SyntaxError) {
      sendJson(res, 400, { error: { code: "INVALID_JSON", message: "Request body must be valid JSON." } });
      return;
    }
    if (error instanceof ApiError) {
      sendJson(res, error.statusCode, {
        error: {
          code: error.code,
          message: error.message,
          retryable: error.retryable,
          ...(error.details === undefined ? {} : { details: error.details }),
        },
      });
      return;
    }
    requestLogger.error("request failed", { error: error instanceof Error ? error.message : String(error) });
    sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
  }
});

server.listen(PORT, () => {
  console.log(`Swee SG REST gateway listening on http://localhost:${PORT}`);
  console.log(`tools: ${enabledTools.length}/${ALL_TOOL_DEFINITIONS.length} (toolsets: ${[...enabledToolsets].join(",")})`);
  console.log(`try: curl http://localhost:${PORT}/api/v1/pulse/snapshot`);
});
