import { createServer } from "node:http";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { spawn } from "node:child_process";
import net from "node:net";
import { chromium } from "playwright";

const root = resolve(import.meta.dirname, "..");
const artifactDir = resolve(root, "output/playwright");
mkdirSync(artifactDir, { recursive: true });

const consoleMessages = [];
const serverMessages = [];

const pulseSnapshot = {
  generatedAt: "2026-05-22T00:00:00.000Z",
  signals: [
    {
      id: "mobility-incident-1",
      category: "mobility",
      severity: "watch",
      title: "CTE incident",
      description: "Fixture traffic incident on CTE toward city.",
      source: "LTA DataMall fixture",
      sourceTool: "sg_lta_traffic_incidents",
      observedAt: "2026-05-22T00:00:00.000Z",
      upstreamTimestamp: "2026-05-22T00:00:00.000Z",
      area: "Central",
      recommendedAction: "Check alternate route before dispatch.",
    },
    {
      id: "weather-rain-1",
      category: "weather",
      severity: "watch",
      title: "Rainfall detected",
      description: "Fixture rainfall station reported recent precipitation.",
      source: "NEA fixture",
      sourceTool: "sg_nea_rainfall",
      observedAt: "2026-05-22T00:00:00.000Z",
      upstreamTimestamp: "2026-05-22T00:00:00.000Z",
      area: "Islandwide",
      recommendedAction: "Monitor outdoor operations and commute plans.",
    },
    {
      id: "source-health-1",
      category: "source_health",
      severity: "info",
      title: "Sources reachable",
      description: "Fixture NEA and LTA sources are reachable.",
      source: "Swee Pulse fixture",
      sourceTool: "swee_pulse_snapshot",
      observedAt: "2026-05-22T00:00:00.000Z",
      upstreamTimestamp: null,
      recommendedAction: "Review source rows before acting on a signal.",
    },
  ],
  sourceHealth: [
    {
      source: "LTA DataMall fixture",
      sourceTool: "sg_lta_traffic_incidents",
      status: "ready",
      observedAt: "2026-05-22T00:00:00.000Z",
      recordCount: 1,
    },
    {
      source: "NEA fixture",
      sourceTool: "sg_nea_rainfall",
      status: "ready",
      observedAt: "2026-05-22T00:00:00.000Z",
      recordCount: 1,
    },
  ],
  gaps: [
    {
      code: "TRAFFIC_IMAGES_NOT_CHECKED",
      message: "Fixture smoke does not fetch live traffic camera images.",
    },
  ],
};

const shieldAudits = [
  {
    auditId: "audit_fixture_1",
    requestId: "request_fixture_1",
    traceId: "trace_fixture_1",
    toolName: "swee_pulse_snapshot",
    status: "success",
    startedAt: "2026-05-22T00:00:00.000Z",
    finishedAt: "2026-05-22T00:00:00.050Z",
    durationMs: 50,
    decision: {
      decision: "allow",
      riskLevel: "low",
      reasons: ["fixture public-data call"],
      tags: ["pulse"],
      mode: "observe",
    },
  },
];

const jsonResponse = (response, statusCode, payload) => {
  response.writeHead(statusCode, {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify(payload));
};

const createMockGateway = () => createServer((request, response) => {
  const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
  serverMessages.push(`${request.method} ${requestUrl.pathname}${requestUrl.search}`);

  if (request.method === "OPTIONS") {
    response.writeHead(204, {
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Origin": "*",
    });
    response.end();
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/v1/health") {
    jsonResponse(response, 200, { status: "ok", readiness: "ready", tools: 100 });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/v1/pulse/snapshot") {
    jsonResponse(response, 200, {
      data: { snapshot: pulseSnapshot },
      shield: { auditId: "audit_fixture_1", decision: "allow", riskLevel: "low" },
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/v1/shield/audits") {
    jsonResponse(response, 200, { records: shieldAudits });
    return;
  }

  jsonResponse(response, 404, {
    error: {
      code: "FIXTURE_ROUTE_NOT_FOUND",
      message: `No browser smoke fixture for ${request.method} ${requestUrl.pathname}.`,
    },
  });
});

const listen = (server) =>
  new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(0, "127.0.0.1", () => {
      server.off("error", rejectListen);
      const address = server.address();
      if (address === null || typeof address === "string") {
        rejectListen(new Error("Gateway fixture did not expose a TCP port."));
        return;
      }
      resolveListen(address.port);
    });
  });

const getFreePort = () =>
  new Promise((resolvePort, rejectPort) => {
    const server = net.createServer();
    server.once("error", rejectPort);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address === null || typeof address === "string") {
        rejectPort(new Error("Unable to allocate a TCP port."));
        return;
      }
      server.close(() => resolvePort(address.port));
    });
  });

const waitForHttp = async (url, timeoutMs = 15000) => {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = new Error(`${url} returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await delay(250);
  }
  throw lastError ?? new Error(`Timed out waiting for ${url}`);
};

const startVite = (webPort, gatewayPort) => {
  const child = spawn(
    "npm",
    ["run", "dev", "-w", "apps/web", "--", "--host", "127.0.0.1", "--port", String(webPort), "--strictPort"],
    {
      cwd: root,
      env: {
        ...process.env,
        BROWSER: "none",
        VITE_API_BASE_URL: `http://127.0.0.1:${gatewayPort}`,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  child.stdout.on("data", (chunk) => serverMessages.push(`[vite] ${chunk.toString().trimEnd()}`));
  child.stderr.on("data", (chunk) => serverMessages.push(`[vite] ${chunk.toString().trimEnd()}`));
  return child;
};

const stopChild = async (child) => {
  if (child.exitCode !== null || child.signalCode !== null) return;
  child.kill("SIGTERM");
  const exited = await Promise.race([
    new Promise((resolveExit) => child.once("exit", resolveExit)),
    delay(3000).then(() => false),
  ]);
  if (exited === false && child.exitCode === null && child.signalCode === null) {
    child.kill("SIGKILL");
  }
};

const writeDiagnostics = async (page, name) => {
  if (page !== null && !page.isClosed()) {
    await page.screenshot({ path: resolve(artifactDir, `${name}.png`), fullPage: true }).catch(() => undefined);
  }
  writeFileSync(resolve(artifactDir, "browser-console.log"), `${consoleMessages.join("\n")}\n`);
  writeFileSync(resolve(artifactDir, "servers.log"), `${serverMessages.join("\n")}\n`);
};

const assertNoDocumentOverflow = async (page, label) => {
  const metrics = await page.evaluate(() => ({
    bodyScrollWidth: document.body.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  const overflow = Math.max(metrics.scrollWidth, metrics.bodyScrollWidth) - metrics.clientWidth;
  if (overflow > 1) {
    throw new Error(`${label} overflows horizontally by ${overflow}px (${JSON.stringify(metrics)})`);
  }
};

let mockGateway = null;
let vite = null;
let browser = null;
let page = null;

try {
  mockGateway = createMockGateway();
  const gatewayPort = await listen(mockGateway);
  const webPort = await getFreePort();
  const webBaseUrl = `http://127.0.0.1:${webPort}`;

  vite = startVite(webPort, gatewayPort);
  await waitForHttp(webBaseUrl);

  browser = await chromium.launch();
  const context = await browser.newContext({
    baseURL: webBaseUrl,
    viewport: { width: 1280, height: 900 },
  });
  page = await context.newPage();
  page.on("console", (message) => consoleMessages.push(`[${message.type()}] ${message.text()}`));
  page.on("pageerror", (error) => consoleMessages.push(`[pageerror] ${error.stack ?? error.message}`));

  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Swee SG" }).waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Watch" }).waitFor({ state: "visible" });
  await page.getByText("2 signals need review across mobility and weather.").waitFor({ state: "visible" });
  await page.getByText("1 coverage gap limits confidence").waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Coverage Gaps" }).waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Needs Attention" }).waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Mobility" }).waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Weather" }).waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Source Health" }).waitFor({ state: "visible" });
  await page.getByText("Ops: Shield Audit (1)").waitFor({ state: "visible" });
  await page.getByText("CTE incident").waitFor({ state: "visible" });
  await page.getByText("Rainfall detected").waitFor({ state: "visible" });
  await page.getByText("TRAFFIC_IMAGES_NOT_CHECKED").waitFor({ state: "visible" });
  await page.getByText("swee_pulse_snapshot").first().waitFor({ state: "attached" });
  await assertNoDocumentOverflow(page, "Swee Pulse desktop layout");
  await page.setViewportSize({ width: 390, height: 844 });
  await assertNoDocumentOverflow(page, "Swee Pulse mobile layout");

  await writeDiagnostics(page, "web-smoke-success");
  writeFileSync(resolve(artifactDir, "first-run-artifact-manifest.json"), `${JSON.stringify({
    schemaVersion: "swee-sg-web-smoke/v1",
    observedAt: new Date().toISOString(),
    command: "npm run test:smoke:web",
    entrypoint: { route: "/", gatewayRoute: "GET /api/v1/pulse/snapshot" },
    boundary: {
      mode: "fixture",
      liveUpstreamCalls: false,
      fixtureGateway: "scripts/browser-smoke-web.mjs",
      note: "This pack proves the no-auth Swee Pulse dashboard shell, source-health rows, Shield audit rows, and responsive layout.",
    },
    artifacts: [{ path: "web-smoke-success.png", role: "browser screenshot of the successful smoke flow" }],
    sourceFreshness: pulseSnapshot.sourceHealth,
    gaps: pulseSnapshot.gaps,
    shieldAudits,
  }, null, 2)}\n`);

  process.stdout.write(JSON.stringify({
    ok: true,
    webBaseUrl,
    gatewayBaseUrl: `http://127.0.0.1:${gatewayPort}`,
    manifest: "first-run-artifact-manifest.json",
    artifacts: "output/playwright",
  }, null, 2));
  process.stdout.write("\n");
} catch (error) {
  await writeDiagnostics(page, "web-smoke-failure");
  if (
    error instanceof Error
    && /Executable doesn't exist|browserType.launch/i.test(error.message)
  ) {
    error.message = `${error.message}\nRun: npx playwright install chromium`;
  }
  throw error;
} finally {
  if (browser !== null) {
    await browser.close().catch(() => undefined);
  }
  if (vite !== null) {
    await stopChild(vite);
  }
  if (mockGateway !== null) {
    await new Promise((resolveClose) => mockGateway.close(resolveClose));
  }
}
