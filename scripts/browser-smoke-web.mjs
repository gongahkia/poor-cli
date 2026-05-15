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

const dossierFixture = {
  title: "DBS BANK LTD",
  summary: [
    { label: "Entity", value: "DBS BANK LTD", source: "ACRA fixture" },
    { label: "UEN", value: "03591300B", source: "ACRA fixture" },
    { label: "Entity status", value: "Live", source: "ACRA fixture" },
  ],
  evidence: [
    {
      label: "Identity match",
      value: "Fixture matched DBS BANK search to UEN 03591300B through the ACRA identity module.",
      source: "sg_business_dossier fixture",
    },
  ],
  records: {
    resolution: {
      requestedEntityName: "DBS BANK",
      requestedUen: null,
      selectedModules: ["acra", "gebiz"],
      searchedModules: ["acra", "gebiz"],
      matchedModules: ["acra"],
      unmatchedModules: ["gebiz"],
      unsearchedModules: ["bca", "boa", "cea", "hsa", "hlb"],
      inferredSectors: [
        {
          sector: "finance",
          source: "ACRA primary SSIC",
          evidence: "64120 - Full banks",
          modules: ["acra"],
        },
      ],
      moduleReasons: [
        {
          module: "acra",
          status: "matched",
          selectedBy: ["default"],
          searched: true,
          matched: true,
          reason: "Default identity module returned one public registry match.",
          inferredSectors: ["finance"],
        },
        {
          module: "gebiz",
          status: "unmatched",
          selectedBy: ["default"],
          searched: true,
          matched: false,
          reason: "Procurement fixture ran and returned no matching public tender records.",
        },
      ],
    },
    quality: {
      dossierConfidence: {
        level: "high",
        score: 0.93,
        rationale: "Fixture contains an exact ACRA identity match and bounded public-data gaps.",
        identity: {
          level: "high",
          score: 1,
          primarySource: "ACRA fixture",
          matchedOn: "uen",
          rationale: "The fixture route intentionally resolves DBS BANK to UEN 03591300B.",
        },
        coverage: {
          selectedModules: ["acra", "gebiz"],
          searchedModules: ["acra", "gebiz"],
          matchedModules: ["acra"],
          unmatchedModules: ["gebiz"],
          unsearchedModules: ["bca", "boa", "cea", "hsa", "hlb"],
          score: 0.5,
          rationale: "Only identity and procurement modules are covered by this smoke fixture.",
        },
      },
    },
    acra: [
      {
        uen: "03591300B",
        entityName: "DBS BANK LTD",
        entityStatusDescription: "Live",
        entityTypeDescription: "Local Company",
        registrationIncorporationDate: "1968-07-16",
        block: "12",
        streetName: "Marina Boulevard",
        buildingName: "Marina Bay Financial Centre",
        postalCode: "018982",
        primarySsicCode: "64120",
        primarySsicDescription: "Full banks",
      },
    ],
    gebizTenders: [],
  },
  gaps: [
    {
      code: "GEBIZ_NO_MATCH",
      message: "No GeBIZ tender award records are returned by the smoke fixture.",
    },
  ],
  provenance: [
    {
      source: "ACRA public search fixture",
      tool: "sg_business_dossier",
      coverage: "Entity identity fixture for browser smoke coverage.",
      authRequired: false,
      recordCount: 1,
      sourceUrl: "https://data.gov.sg/",
      evidenceType: "official_registry",
    },
    {
      source: "GeBIZ public tender fixture",
      tool: "sg_business_dossier",
      coverage: "Procurement gap fixture.",
      authRequired: false,
      recordCount: 0,
      sourceUrl: "https://www.gebiz.gov.sg/",
      evidenceType: "official_registry",
    },
  ],
  freshness: [
    {
      source: "ACRA public search fixture",
      observedAt: "2026-05-15T00:00:00.000Z",
      upstreamTimestamp: "2026-05-14",
    },
  ],
  limits: [
    {
      code: "PUBLIC_DATA_ONLY",
      message: "The browser smoke fixture covers public registry surfaces only; it does not assert directors, shareholders, or beneficial ownership.",
    },
  ],
  riskFlags: [
    {
      code: "GEBIZ_NO_MATCH",
      severity: "low",
      message: "No public procurement records are returned by the fixture.",
      source: "GeBIZ fixture",
    },
  ],
  matchConfidence: [
    {
      source: "ACRA fixture",
      confidence: "exact",
      matchedOn: "uen",
    },
  ],
  nextChecks: [
    {
      tool: "sg_acra_entities",
      reason: "Re-run direct ACRA identity lookup when validating against live public data.",
      input: { uen: "03591300B" },
    },
  ],
};

const jsonResponse = (response, statusCode, payload) => {
  response.writeHead(statusCode, {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify(payload));
};

const readRequestBody = (request) =>
  new Promise((resolveBody, rejectBody) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => resolveBody(body));
    request.on("error", rejectBody);
  });

const createMockGateway = () => createServer(async (request, response) => {
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
    jsonResponse(response, 200, {
      status: "ok",
      readiness: "ready",
      tools: 105,
      runtime: {
        startedAt: "2026-05-15T00:00:00.000Z",
        uptimeSeconds: 10,
        observedAt: "2026-05-15T00:00:10.000Z",
      },
      services: {
        gateway: {
          status: "ready",
          message: "Fixture gateway is reachable.",
          observedAt: "2026-05-15T00:00:10.000Z",
          latencyMs: 1,
        },
      },
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/v1/dude/search-suggestions") {
    jsonResponse(response, 200, {
      query: requestUrl.searchParams.get("q") ?? "",
      suggestions: [
        {
          id: "03591300B",
          label: "DBS BANK LTD",
          description: "03591300B - Live - Local Company",
          uen: "03591300B",
          entityName: "DBS BANK LTD",
          status: "Live",
          entityTypeDescription: "Local Company",
        },
      ],
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/v1/dude/web-presence") {
    jsonResponse(response, 200, {
      query: requestUrl.searchParams.get("query") ?? "DBS BANK LTD 03591300B",
      configured: true,
      results: [
        {
          title: "DBS Bank Singapore",
          snippet: "Fixture web result for browser smoke coverage.",
          url: "https://www.dbs.com.sg/",
          siteName: "DBS",
          position: 1,
        },
      ],
      possibleOfficialWebsite: "https://www.dbs.com.sg/",
      limits: ["Fixture web discovery does not perform live search."],
    });
    return;
  }

  if (request.method === "POST" && requestUrl.pathname === "/api/v1/sg_business_dossier") {
    const rawBody = await readRequestBody(request);
    const body = rawBody.trim() === "" ? {} : JSON.parse(rawBody);
    if (body.uen !== "03591300B" && body.entityName !== "DBS BANK LTD" && body.entityName !== "DBS BANK") {
      jsonResponse(response, 404, {
        error: {
          code: "FIXTURE_NOT_FOUND",
          message: "Browser smoke fixture only serves DBS BANK / 03591300B.",
        },
      });
      return;
    }
    jsonResponse(response, 200, {
      content: [
        {
          type: "text",
          text: "DBS BANK LTD fixture dossier.",
        },
      ],
      data: {
        record: dossierFixture,
      },
    });
    return;
  }

  if (request.method === "POST" && requestUrl.pathname === "/api/v1/dude/memo") {
    await readRequestBody(request);
    jsonResponse(response, 200, {
      status: "ready",
      configured: true,
      provider: "openai",
      model: "fixture-model",
      generatedAt: "2026-05-15T00:00:00.000Z",
      evidenceMemo: [
        {
          text: "DBS BANK LTD is present in the ACRA fixture summary.",
          citationIds: ["summary-1"],
        },
      ],
      riskRating: {
        level: "medium",
        rationale: "The fixture includes partial module coverage for procurement evidence.",
        citationIds: ["risk-1"],
        confidenceBlockers: ["GeBIZ did not return a matching fixture record."],
      },
      decisionAid: {
        nextSteps: ["Run direct procurement follow-up only if public-sector award history matters operationally."],
        confidenceBlockers: ["The fixture covers only ACRA and GeBIZ modules."],
        nonAdvisoryReminder: "Operational follow-up only; this is not legal, tax, credit, investment, or licensed-advisor advice.",
      },
      citations: [
        {
          id: "summary-1",
          label: "Entity",
          source: "ACRA fixture",
          text: "Entity: DBS BANK LTD",
        },
        {
          id: "risk-1",
          label: "PARTIAL_MODULE_COVERAGE",
          source: "Resolver fixture",
          text: "medium: Matched 1 of 2 searched modules.",
        },
      ],
      gaps: dossierFixture.gaps,
      limits: dossierFixture.limits,
      rejectedClaims: [],
    });
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
        VITE_REST_GATEWAY_URL: `http://127.0.0.1:${gatewayPort}`,
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
  writeFileSync(resolve(artifactDir, "browser-console.log"), consoleMessages.join("\n") + "\n");
  writeFileSync(resolve(artifactDir, "servers.log"), serverMessages.join("\n") + "\n");
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
    acceptDownloads: true,
    baseURL: webBaseUrl,
    viewport: { width: 1280, height: 900 },
  });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: webBaseUrl });
  page = await context.newPage();
  page.on("console", (message) => consoleMessages.push(`[${message.type()}] ${message.text()}`));
  page.on("pageerror", (error) => consoleMessages.push(`[pageerror] ${error.stack ?? error.message}`));

  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: /Singapore due diligence/i }).waitFor({ state: "visible" });
  await page.getByLabel("Company name or UEN").fill("DBS BANK");
  await page.getByRole("button", { name: /DBS BANK LTD/i }).waitFor({ state: "visible" });
  await page.getByRole("button", { name: /DBS BANK LTD/i }).click();
  await page.waitForURL(/\/c\/03591300B(?:\?memo=[a-z]+)?$/);
  await page.getByRole("heading", { name: "DBS BANK LTD" }).waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Summary" }).waitFor({ state: "visible" });
  await page.getByText("ACRA public search fixture").first().waitFor({ state: "visible" });
  await page.getByRole("heading", { name: "Analyst Memo" }).waitFor({ state: "visible" });
  await page.getByText("DBS BANK LTD is present in the ACRA fixture summary.").waitFor({ state: "visible" });
  await assertNoDocumentOverflow(page, "Dossier desktop layout");
  await page.setViewportSize({ width: 390, height: 844 });
  await assertNoDocumentOverflow(page, "Dossier mobile layout");
  await page.setViewportSize({ width: 1280, height: 900 });

  await page.getByRole("button", { name: "Copy link" }).click();
  await page.getByText("Copied").waitFor({ state: "visible" });
  const copiedText = await page.evaluate(() => navigator.clipboard.readText());
  if (!/\/c\/03591300B\?memo=ready$/.test(copiedText)) {
    throw new Error(`Copy link wrote unexpected clipboard text: ${copiedText}`);
  }

  const downloadPromise = page.waitForEvent("download", { timeout: 20000 });
  await page.getByRole("button", { name: "Export PDF" }).click();
  const download = await downloadPromise;
  const suggestedFilename = download.suggestedFilename();
  if (!suggestedFilename.endsWith(".pdf")) {
    throw new Error(`PDF export used unexpected filename: ${suggestedFilename}`);
  }
  await download.saveAs(resolve(artifactDir, suggestedFilename));

  await writeDiagnostics(page, "web-smoke-success");
  process.stdout.write(JSON.stringify({
    ok: true,
    webBaseUrl,
    gatewayBaseUrl: `http://127.0.0.1:${gatewayPort}`,
    pdf: suggestedFilename,
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
