import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const outputPath = resolve(root, "artifacts/datagov-discovery/latest.json");
const markdownPath = resolve(root, "artifacts/datagov-discovery/latest.md");
const generatedAt = process.env["SWEE_DATAGOV_DISCOVERY_GENERATED_AT"] ?? new Date().toISOString();

const QUERY_MATRIX = ["weather", "hawker", "school", "clinic", "park", "water", "community", "transport"];
const SUPPORTED_FORMATS = new Set(["CSV", "JSON", "GEOJSON", "XLSX", "XLS", "TXT"]);

const escapeCell = (value) => String(value ?? "n/a").replaceAll("|", "\\|").replace(/\s+/g, " ").trim();

const classifyError = (error) => {
  const message = error instanceof Error ? error.message : String(error);
  if (/\b(rate limit|too many requests|429)\b/i.test(message)) return "gap";
  return "error";
};

const inspectDataset = async (dataset, client) => {
  try {
    const metadata = await client.getDatasetMetadata(dataset.datasetId);
    if (metadata === null) {
      return {
        datasetId: dataset.datasetId,
        name: dataset.name,
        state: "gap",
        format: dataset.format ?? null,
        metadataReturned: false,
        supportedFormat: false,
        gapCodes: ["METADATA_NOT_RETURNED"],
        gapMessages: ["data.gov.sg metadata returned no dataset record."],
      };
    }
    const format = metadata.format.toUpperCase();
    return {
      datasetId: metadata.datasetId,
      name: metadata.name,
      state: "ready",
      format: metadata.format,
      metadataReturned: true,
      supportedFormat: SUPPORTED_FORMATS.has(format),
      managedByAgencyName: metadata.managedByAgencyName,
      lastUpdatedAt: metadata.lastUpdatedAt,
      gapCodes: SUPPORTED_FORMATS.has(format) ? [] : ["UNSUPPORTED_DISCOVERY_FORMAT"],
      gapMessages: SUPPORTED_FORMATS.has(format) ? [] : [`Discovered dataset uses unsupported format ${metadata.format}.`],
    };
  } catch (error) {
    return {
      datasetId: dataset.datasetId,
      name: dataset.name,
      state: classifyError(error),
      format: dataset.format ?? null,
      metadataReturned: false,
      supportedFormat: false,
      gapCodes: ["METADATA_CHECK_FAILED"],
      gapMessages: [error instanceof Error ? error.message : String(error)],
    };
  }
};

const runQuery = async (query, client) => {
  try {
    const results = await client.searchDatasets(query, 5);
    const topDatasets = [];
    for (const dataset of results.slice(0, 3)) {
      topDatasets.push(await inspectDataset(dataset, client));
    }
    return {
      query,
      state: results.length > 0 ? "ready" : "gap",
      resultCount: results.length,
      topDatasets,
      gapCodes: results.length > 0 ? [] : ["NO_SEARCH_RESULTS"],
      gapMessages: results.length > 0 ? [] : [`data.gov.sg search returned no datasets for ${query}.`],
    };
  } catch (error) {
    return {
      query,
      state: classifyError(error),
      resultCount: 0,
      topDatasets: [],
      gapCodes: ["SEARCH_FAILED"],
      gapMessages: [error instanceof Error ? error.message : String(error)],
    };
  }
};

const writeArtifacts = (artifact) => {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(artifact, null, 2) + "\n");

  mkdirSync(dirname(markdownPath), { recursive: true });
  const markdown = [
    "# Swee data.gov.sg Discovery Quality Benchmark",
    "",
    `Generated: ${artifact.generatedAt}`,
    "",
    "| Query | State | Results | Top datasets | Gaps |",
    "| --- | --- | ---: | --- | --- |",
    ...artifact.queries.map((item) =>
      `| ${escapeCell(item.query)} | ${escapeCell(item.state)} | ${item.resultCount} | ${escapeCell(item.topDatasets.map((dataset) => `${dataset.datasetId}:${dataset.format ?? "n/a"}`).join(", ") || "none")} | ${escapeCell(item.gapCodes.join(", ") || "none")} |`,
    ),
    "",
    "## Limits",
    "",
    ...artifact.limits.map((limit) => `- ${limit}`),
    "",
  ].join("\n");
  writeFileSync(markdownPath, markdown);
};

const main = async () => {
  const stateDir = mkdtempSync(resolve(tmpdir(), "swee-datagov-discovery-"));
  const previousStateDir = process.env["SG_APIS_STATE_DIR"];
  process.env["SG_APIS_STATE_DIR"] = stateDir;
  try {
    const client = await import(pathToFileURL(resolve(root, "packages/mcp-server/dist/apis/datagov/client.js")).href);
    const queries = [];
    for (const query of QUERY_MATRIX) {
      queries.push(await runQuery(query, client));
    }
    const artifact = {
      schemaVersion: "swee-datagov-discovery-live-benchmark/v1",
      generatedAt,
      source: "local-live-datagov",
      command: "npm run benchmark:datagov:discovery:live",
      queries,
      limits: [
        "This artifact checks bounded data.gov.sg discovery quality only; it is not source completeness evidence.",
        "Supported format means the current runtime has a reader path for the discovered dataset format.",
        "Empty results and rate limits are reported as source gaps instead of being filled with synthetic matches.",
      ],
    };
    writeArtifacts(artifact);
    process.stdout.write(`${JSON.stringify({
      ok: true,
      output: outputPath,
      markdown: markdownPath,
      states: Object.fromEntries(queries.map((query) => [query.query, query.state])),
    }, null, 2)}\n`);
  } finally {
    if (previousStateDir === undefined) {
      delete process.env["SG_APIS_STATE_DIR"];
    } else {
      process.env["SG_APIS_STATE_DIR"] = previousStateDir;
    }
    rmSync(stateDir, { recursive: true, force: true });
  }
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.stderr.write("Run npm run build first. Discovery gaps should be written into the artifact instead of becoming invented source values.\n");
  process.exit(1);
});
