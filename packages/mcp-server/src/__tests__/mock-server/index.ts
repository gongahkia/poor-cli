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
  "/datagov/datasets/": "datagov/__tests__/fixtures/metadata-response.json",
  "/datagov/datasets": "datagov/__tests__/fixtures/search-response.json",
  "/lta/v3/BusArrival": "lta/__tests__/fixtures/bus-arrivals-response.json",
  "/lta/TrainServiceAlerts": "lta/__tests__/fixtures/train-alerts-response.json",
  "/lta/TrafficIncidents": "lta/__tests__/fixtures/traffic-incidents-response.json",
  "/nea/two-hr-forecast": "nea/__tests__/fixtures/forecast-response.json",
  "/nea/psi": "nea/__tests__/fixtures/psi-response.json",
  "/nea/pm25": "nea/__tests__/fixtures/pm25-response.json",
  "/nea/rainfall": "nea/__tests__/fixtures/rainfall-response.json",
};

const DATASTORE_FIXTURES_BY_RESOURCE_ID: Record<string, string> = {
  d_8b84c4ee58e3cfc0ece0d773c8ca6abc: "hdb/__tests__/fixtures/resale-response.json",
  d_c9f57187485a850908655db0e8cfe651: "hdb/__tests__/fixtures/rental-response.json",
  d_8575e84912df3c28995b8e6e0e05205a: "acra/__tests__/fixtures/search-response.json",
  d_19573c579879be15623f2e1e3854926d: "bca/__tests__/fixtures/licensed-builders-response.json",
  d_dcda79be4aded5f9e769b8e23ff69b47: "bca/__tests__/fixtures/registered-contractors-response.json",
  d_07c63be0f37e6e59c07a4ddc2fd87fcb: "cea/__tests__/fixtures/search-response.json",
};

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost`);
  const delay = parseInt(url.searchParams.get("delay") ?? "0", 10);

  const respond = (): void => {
    if (url.pathname === "/datagov/action/datastore_search") {
      const resourceId = url.searchParams.get("resource_id");
      const fixture = resourceId === null
        ? "hdb/__tests__/fixtures/resale-response.json"
        : DATASTORE_FIXTURES_BY_RESOURCE_ID[resourceId] ?? "hdb/__tests__/fixtures/resale-response.json";
      res.writeHead(200, { "Content-Type": "application/json", Token: "mock-daily-token" });
      res.end(loadFixture(fixture));
      return;
    }

    let matched = false;
    const orderedRoutes = Object.entries(ROUTES).sort(([left], [right]) => right.length - left.length);
    for (const [route, fixture] of orderedRoutes) {
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
