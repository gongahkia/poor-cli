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

const loadJsonFixture = (apiPath: string): unknown => {
  return JSON.parse(loadFixture(apiPath));
};

const ROUTES: Record<string, string> = {
  "/singstat/tabledata/": "singstat/__tests__/fixtures/data-response.json",
  "/onemap/common/elastic/search": "onemap/__tests__/fixtures/search-response.json",
  "/onemap/public/revgeocode": "onemap/__tests__/fixtures/reverse-geocode-response.json",
  "/onemap/public/routingsvc/route": "onemap/__tests__/fixtures/route-response.json",
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

const DATASET_DOWNLOADS_BY_ID: Record<
  string,
  {
    readonly path: string;
    readonly fixture: string;
    readonly contentType: string;
  }
> = {
  d_9de02d3fb33d96da1855f4fbef549a0f: {
    path: "/downloads/pa-community-outlets.geojson",
    fixture: "pa/__tests__/fixtures/community-outlets.geojson",
    contentType: "application/geo+json",
  },
  d_9ae25d6b3fefdd15983c4e46ecc7fcbd: {
    path: "/downloads/pa-resident-network-centres.geojson",
    fixture: "pa/__tests__/fixtures/resident-network-centres.geojson",
    contentType: "application/geo+json",
  },
  d_9b87bab59d036a60fad2a91530e10773: {
    path: "/downloads/sportsg-facilities.geojson",
    fixture: "sportsg/__tests__/fixtures/facilities.geojson",
    contentType: "application/geo+json",
  },
  d_5d668e3f544335f8028f546827b773b4: {
    path: "/downloads/ecda-childcare-services.geojson",
    fixture: "ecda/__tests__/fixtures/childcare-services.geojson",
    contentType: "application/geo+json",
  },
  d_696c994c50745b079b3684f0e90ffc53: {
    path: "/downloads/ecda-listing-of-centres.csv",
    fixture: "ecda/__tests__/fixtures/listing-of-centres.csv",
    contentType: "text/csv; charset=utf-8",
  },
  d_add23c06f7267e799185c79ccaa2099b: {
    path: "/downloads/msf-family-services.geojson",
    fixture: "msf/__tests__/fixtures/family-services.geojson",
    contentType: "application/geo+json",
  },
  d_77e6e0d58ce4743dab1f26dfcbbeb6f4: {
    path: "/downloads/msf-student-care-services.geojson",
    fixture: "msf/__tests__/fixtures/student-care-services.geojson",
    contentType: "application/geo+json",
  },
  d_22cfe2aed0bf20a679ab59bcaf0f8248: {
    path: "/downloads/msf-social-service-offices.geojson",
    fixture: "msf/__tests__/fixtures/social-service-offices.geojson",
    contentType: "application/geo+json",
  },
  d_d77de0f78ca589a5c61da7a60fdee6ba: {
    path: "/downloads/boa-architects.csv",
    fixture: "boa/__tests__/fixtures/architects.csv",
    contentType: "text/csv; charset=utf-8",
  },
  d_d5c0a4ffd076a3e40d772275619bbb66: {
    path: "/downloads/boa-architecture-firms.csv",
    fixture: "boa/__tests__/fixtures/architecture-firms.csv",
    contentType: "text/csv; charset=utf-8",
  },
  d_bc50d72a9d61457964c6ea8d8ba7dce2: {
    path: "/downloads/hsa-licensed-pharmacies.csv",
    fixture: "hsa/__tests__/fixtures/licensed-pharmacies.csv",
    contentType: "text/csv; charset=utf-8",
  },
  d_bf50ce0f3f42f69d7acd50635afa62da: {
    path: "/downloads/hsa-health-product-licensees.csv",
    fixture: "hsa/__tests__/fixtures/health-product-licensees.csv",
    contentType: "text/csv; charset=utf-8",
  },
  d_654e22f14e5bb817423f0e0c9ac4f632: {
    path: "/downloads/hlb-hotels.geojson",
    fixture: "hlb/__tests__/fixtures/hotels.geojson",
    contentType: "application/geo+json",
  },
};

const DATASET_DOWNLOADS_BY_PATH = Object.fromEntries(
  Object.values(DATASET_DOWNLOADS_BY_ID).map((download) => [download.path, download]),
);

const DATASTORE_FIXTURES_BY_RESOURCE_ID: Record<string, string> = {
  d_8b84c4ee58e3cfc0ece0d773c8ca6abc: "hdb/__tests__/fixtures/resale-response.json",
  d_c9f57187485a850908655db0e8cfe651: "hdb/__tests__/fixtures/rental-response.json",
  d_8575e84912df3c28995b8e6e0e05205a: "acra/__tests__/fixtures/search-response.json",
  d_acbc938ec77af18f94cecc4a7c9ec720: "acra/__tests__/fixtures/search-response.json",
  d_9af9317c646a1c881bb5591c91817cc6: "acra/__tests__/fixtures/search-response.json",
  d_4e3db8955fdcda6f9944097bef3d2724: "acra/__tests__/fixtures/search-response.json",
  d_19573c579879be15623f2e1e3854926d: "bca/__tests__/fixtures/licensed-builders-response.json",
  d_dcda79be4aded5f9e769b8e23ff69b47: "bca/__tests__/fixtures/registered-contractors-response.json",
  d_07c63be0f37e6e59c07a4ddc2fd87fcb: "cea/__tests__/fixtures/search-response.json",
  d_c9bea4c28194866ab2e1313e6be430d6: "gebiz/__tests__/fixtures/search-response.json",
};

const MAS_FIXTURES_BY_RESOURCE_ID: Record<string, string> = {
  "95932927-c8bc-4e7a-b484-68a66a24edfe": "mas/__tests__/fixtures/search-response.json",
  "9a0bf149-308c-4bd2-832d-76c8e6cb47ed": "mas/__tests__/fixtures/search-response-sora.json",
  "5f2b18a8-0883-4e5b-9dc7-990de1383525": "mas/__tests__/fixtures/search-response-banking.json",
};

type DatastoreRecord = Record<string, unknown>;

type DatastoreFixture = {
  readonly success: true;
  readonly result: {
    readonly fields: readonly { readonly id: string; readonly type: string }[];
    readonly records: readonly DatastoreRecord[];
    readonly total: number;
    readonly limit: number;
    readonly offset: number;
  };
};

const normalizeScalar = (value: unknown): string => {
  return String(value ?? "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
};

const recordMatchesFilter = (
  record: DatastoreRecord,
  field: string,
  filterValue: unknown,
): boolean => {
  const actual = normalizeScalar(record[field]);

  if (filterValue !== null && typeof filterValue === "object" && !Array.isArray(filterValue)) {
    const ilike = (filterValue as { ilike?: unknown }).ilike;
    if (typeof ilike === "string") {
      return actual.includes(normalizeScalar(ilike));
    }
  }

  return actual === normalizeScalar(filterValue);
};

const applyDatastoreFilters = (
  records: readonly DatastoreRecord[],
  filters: Readonly<Record<string, unknown>> | null,
): readonly DatastoreRecord[] => {
  if (filters === null || Object.keys(filters).length === 0) {
    return records;
  }

  return records.filter((record) =>
    Object.entries(filters).every(([field, value]) => recordMatchesFilter(record, field, value)),
  );
};

const applyDatastoreSort = (
  records: readonly DatastoreRecord[],
  sort: string | null,
): readonly DatastoreRecord[] => {
  if (sort === null || sort.trim() === "") {
    return records;
  }

  const [field, direction] = sort.trim().split(/\s+/, 2);
  if (field === undefined || field === "") {
    return records;
  }

  const multiplier = direction?.toLowerCase() === "desc" ? -1 : 1;

  return [...records].sort((left, right) => {
    const leftValue = left[field];
    const rightValue = right[field];

    if (typeof leftValue === "number" && typeof rightValue === "number") {
      return (leftValue - rightValue) * multiplier;
    }

    return normalizeScalar(leftValue).localeCompare(normalizeScalar(rightValue)) * multiplier;
  });
};

const buildDatastorePayload = (
  fixturePath: string,
  url: URL,
): DatastoreFixture => {
  const payload = loadJsonFixture(fixturePath) as DatastoreFixture;
  const rawFilters = url.searchParams.get("filters");
  const filters =
    rawFilters === null
      ? null
      : JSON.parse(rawFilters) as Readonly<Record<string, unknown>>;
  const filteredRecords = applyDatastoreFilters(payload.result.records, filters);
  const sortedRecords = applyDatastoreSort(filteredRecords, url.searchParams.get("sort"));
  const offset = Math.max(parseInt(url.searchParams.get("offset") ?? "0", 10) || 0, 0);
  const requestedLimit = parseInt(url.searchParams.get("limit") ?? "", 10);
  const limit =
    Number.isFinite(requestedLimit) && requestedLimit > 0
      ? requestedLimit
      : payload.result.limit;
  const records = sortedRecords.slice(offset, offset + limit);

  return {
    ...payload,
    result: {
      ...payload.result,
      total: sortedRecords.length,
      offset,
      limit,
      records,
    },
  };
};

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost`);
  const delay = parseInt(url.searchParams.get("delay") ?? "0", 10);

  const respond = (): void => {
    const origin = `http://${req.headers.host ?? "localhost"}`;

    if (url.pathname.startsWith("/datagov-open/datasets/") && url.pathname.endsWith("/poll-download")) {
      const datasetId = url.pathname.split("/")[3];
      const download = datasetId === undefined ? undefined : DATASET_DOWNLOADS_BY_ID[datasetId];
      if (download === undefined) {
        res.writeHead(404, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Dataset download fixture not found", path: url.pathname }));
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        code: 0,
        data: {
          url: `${origin}${download.path}`,
          status: "completed",
        },
        errorMsg: "",
      }));
      return;
    }

    const datasetDownloadFixture = DATASET_DOWNLOADS_BY_PATH[url.pathname];
    if (datasetDownloadFixture !== undefined) {
      res.writeHead(200, { "Content-Type": datasetDownloadFixture.contentType });
      res.end(loadFixture(datasetDownloadFixture.fixture));
      return;
    }

    if (url.pathname.startsWith("/onemap/common/elastic/search")) {
      const searchVal = url.searchParams.get("searchVal");
      const fixture = searchVal === "049178"
        ? "onemap/__tests__/fixtures/search-response-049178.json"
        : searchVal === "048616"
          ? "onemap/__tests__/fixtures/search-response-048616.json"
          : searchVal === "560230"
            ? "onemap/__tests__/fixtures/search-response-560230.json"
          : "onemap/__tests__/fixtures/search-response.json";
      res.writeHead(200, { "Content-Type": "application/json", Token: "mock-daily-token" });
      res.end(loadFixture(fixture));
      return;
    }

    if (url.pathname === "/ura/invokeUraDS") {
      const service = url.searchParams.get("service");
      const fixture =
        service === "GET_PLANNING_AREA"
          ? "ura/__tests__/fixtures/planning-response.json"
          : service === "PMI_Resi_Transaction"
            ? "ura/__tests__/fixtures/property-transactions-response.json"
            : service === "DC_Rates"
              ? "ura/__tests__/fixtures/dev-charges-response.json"
              : "ura/__tests__/fixtures/search-response.json";
      res.writeHead(200, { "Content-Type": "application/json", Token: "mock-daily-token" });
      res.end(loadFixture(fixture));
      return;
    }

    if (url.pathname === "/datagov/action/datastore_search") {
      const resourceId = url.searchParams.get("resource_id");
      const fixture = resourceId === null
        ? "hdb/__tests__/fixtures/resale-response.json"
        : DATASTORE_FIXTURES_BY_RESOURCE_ID[resourceId] ?? "hdb/__tests__/fixtures/resale-response.json";
      res.writeHead(200, { "Content-Type": "application/json", Token: "mock-daily-token" });
      res.end(JSON.stringify(buildDatastorePayload(fixture, url)));
      return;
    }

    if (url.pathname === "/mas/search.json") {
      const resourceId = url.searchParams.get("resource_id");
      const fixture = resourceId === null
        ? "mas/__tests__/fixtures/search-response.json"
        : MAS_FIXTURES_BY_RESOURCE_ID[resourceId] ?? "mas/__tests__/fixtures/search-response.json";
      res.writeHead(200, { "Content-Type": "application/json", Token: "mock-daily-token" });
      res.end(loadFixture(fixture));
      return;
    }

    if (url.pathname === "/singstat/resourceId") {
      const keyword = (url.searchParams.get("keyword") ?? "").toLowerCase();
      const fixture = keyword.includes("cpi") || keyword.includes("inflation")
        ? "singstat/__tests__/fixtures/search-response-cpi.json"
        : "singstat/__tests__/fixtures/search-response.json";
      const payload = loadJsonFixture(fixture) as {
        Data: {
          records: readonly unknown[];
          total: number;
        };
      };
      const requestedLimit = Number.parseInt(url.searchParams.get("limit") ?? "", 10);
      const effectiveLimit = Number.isFinite(requestedLimit) && requestedLimit > 0
        ? requestedLimit
        : payload.Data.records.length;
      const records = payload.Data.records.slice(0, effectiveLimit);
      res.writeHead(200, { "Content-Type": "application/json", Token: "mock-daily-token" });
      res.end(JSON.stringify({
        ...payload,
        Data: {
          ...payload.Data,
          total: records.length,
          records,
        },
      }));
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
