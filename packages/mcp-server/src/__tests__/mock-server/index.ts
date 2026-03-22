import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const loadFixture = (apiPath: string): string => {
  try {
    const fixturePath = join(__dirname, "..", "..", "apis", apiPath);
    return readFileSync(fixturePath, "utf-8");
  } catch {
    return JSON.stringify({ error: "Fixture not found", path: apiPath });
  }
};

const ROUTES: Record<string, string> = {
  "/singstat/resourceId": "singstat/__tests__/fixtures/search-response.json",
  "/singstat/tabledata/": "singstat/__tests__/fixtures/data-response.json",
  "/mas/search.json": "mas/__tests__/fixtures/search-response.json",
  "/onemap/common/elastic/search": "onemap/__tests__/fixtures/search-response.json",
  "/ura/invokeUraDS": "ura/__tests__/fixtures/search-response.json",
  "/ura/insertNewToken.action": "ura/__tests__/fixtures/search-response.json",
  "/datagov/datasets": "datagov/__tests__/fixtures/search-response.json",
};

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost`);
  const delay = parseInt(url.searchParams.get("delay") ?? "0", 10);

  const respond = (): void => {
    let matched = false;
    for (const [route, fixture] of Object.entries(ROUTES)) {
      if (url.pathname.startsWith(route)) {
        res.writeHead(200, { "Content-Type": "application/json", Token: "mock-daily-token" });
        res.end(loadFixture(fixture));
        matched = true;
        break;
      }
    }

    if (!matched) {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Not found", path: url.pathname }));
    }
  };

  if (delay > 0) {
    setTimeout(respond, delay);
  } else {
    respond();
  }
});

const PORT = parseInt(process.env["MOCK_PORT"] ?? "0", 10);
server.listen(PORT, () => {
  const addr = server.address();
  const port = typeof addr === "object" && addr !== null ? addr.port : PORT;
  process.stderr.write(`Mock API server running on http://localhost:${port}\n`);
});

export { server };
