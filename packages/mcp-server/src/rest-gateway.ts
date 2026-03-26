#!/usr/bin/env node
// REST gateway: exposes sg_* tools as HTTP POST endpoints
// usage: node packages/mcp-server/dist/rest-gateway.js
// env: PORT (default 3000)
import { createServer } from "node:http";
import { ALL_TOOL_DEFINITIONS } from "./tools/tool-set.js";

const PORT = Number(process.env["PORT"] ?? 3000);

const toolMap = new Map(ALL_TOOL_DEFINITIONS.map((t) => [t.name, t]));

const readBody = (req: import("node:http").IncomingMessage): Promise<string> =>
  new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
    req.on("error", reject);
  });

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  res.setHeader("Content-Type", "application/json");

  // GET /api/v1/tools — list all tools
  if (req.method === "GET" && url.pathname === "/api/v1/tools") {
    res.end(JSON.stringify(ALL_TOOL_DEFINITIONS.map((t) => ({ name: t.name, description: t.description }))));
    return;
  }

  // GET /api/v1/health
  if (req.method === "GET" && url.pathname === "/api/v1/health") {
    res.end(JSON.stringify({ status: "ok", tools: ALL_TOOL_DEFINITIONS.length }));
    return;
  }

  // POST /api/v1/<tool-name>
  if (req.method === "POST" && url.pathname.startsWith("/api/v1/")) {
    const toolName = url.pathname.slice(8).replace(/-/g, "_"); // normalize kebab to snake
    const tool = toolMap.get(toolName) ?? toolMap.get(`sg_${toolName}`);
    if (!tool) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: `tool not found: ${toolName}` }));
      return;
    }
    try {
      const body = await readBody(req);
      const input = body ? JSON.parse(body) : {};
      const result = await tool.handler(input);
      const status = result.isError ? 400 : 200;
      res.writeHead(status);
      res.end(JSON.stringify({
        content: result.content,
        ...(result.structuredContent ? { data: result.structuredContent } : {}),
      }));
    } catch (err) {
      res.writeHead(500);
      res.end(JSON.stringify({ error: err instanceof Error ? err.message : String(err) }));
    }
    return;
  }

  // fallback
  res.writeHead(404);
  res.end(JSON.stringify({
    error: "not found",
    hint: "GET /api/v1/tools for available endpoints, POST /api/v1/<tool-name> to call a tool",
  }));
});

server.listen(PORT, () => {
  console.log(`sg-apis REST gateway listening on http://localhost:${PORT}`);
  console.log(`tools: ${ALL_TOOL_DEFINITIONS.length}`);
  console.log(`try: curl -X POST http://localhost:${PORT}/api/v1/sg_nea_forecast_2hr -d '{"area":"Bedok"}'`);
});
