import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const outputPath = resolve(root, "artifacts/sources/contracts-latest.json");
const markdownPath = resolve(root, "artifacts/sources/contracts-latest.md");
const generatedAt = process.env["SWEE_SOURCE_CONTRACTS_GENERATED_AT"] ?? new Date().toISOString();

const DATASET_DOWNLOAD_PAUSE_MS = 11000;

const CONTRACTS = [
  {
    sourceTool: "sg_hawker_closures",
    source: "NEA via data.gov.sg",
    datasetId: "d_bda4baa634dd1cc7a6c7cad5f19e2d68",
    reader: "datastore",
    expectedFormat: "CSV",
    expectedFields: ["name", "q1_cleaningstartdate", "q4_cleaningenddate"],
  },
  {
    sourceTool: "sg_nlb_libraries",
    source: "NLB via data.gov.sg",
    datasetId: "d_27b8dae65d9ca1539e14d09578b17cbf",
    reader: "geojson",
    expectedFormat: "GEOJSON",
    expectedFields: ["Description"],
  },
  {
    sourceTool: "sg_sportsg_facilities",
    source: "SportSG via data.gov.sg",
    datasetId: "d_9b87bab59d036a60fad2a91530e10773",
    reader: "geojson",
    expectedFormat: "GEOJSON",
    expectedFields: ["VENUE", "POSTAL_CODE", "FMEL_UPD_D"],
  },
  {
    sourceTool: "sg_nparks_parks",
    source: "NParks via data.gov.sg",
    datasetId: "d_77d7ec97be83d44f61b85454f844382f",
    reader: "geojson",
    expectedFormat: "GEOJSON",
    expectedFields: ["NAME", "FMEL_UPD_D"],
  },
  {
    sourceTool: "sg_pub_water_levels",
    source: "PUB via data.gov.sg",
    datasetId: "d_31333fa5cf0834f012d840365b336610",
    reader: "xlsx",
    expectedFormat: "XLSX",
    expectedFields: ["Station ID", "Station Name", "X", "Y"],
  },
  {
    sourceTool: "sg_pa_community_outlets",
    source: "People's Association via data.gov.sg",
    datasetId: "d_9de02d3fb33d96da1855f4fbef549a0f",
    reader: "geojson",
    expectedFormat: "GEOJSON",
    expectedFields: ["NAME", "ADDRESSPOSTALCODE", "FMEL_UPD_D"],
  },
  {
    sourceTool: "sg_moe_schools",
    source: "MOE via data.gov.sg",
    datasetId: "d_688b934f82c1059ed0a6993d2a829089",
    reader: "datastore",
    expectedFormat: "CSV",
    expectedFields: ["school_name", "postal_code", "mainlevel_code"],
  },
  {
    sourceTool: "sg_ecda_childcare_centres",
    source: "ECDA via data.gov.sg",
    datasetId: "d_5d668e3f544335f8028f546827b773b4",
    reader: "geojson",
    expectedFormat: "GEOJSON",
    expectedFields: ["NAME", "ADDRESSPOSTALCODE", "FMEL_UPD_D"],
  },
  {
    sourceTool: "sg_ecda_childcare_centres",
    source: "ECDA via data.gov.sg",
    datasetId: "d_696c994c50745b079b3684f0e90ffc53",
    reader: "csv",
    expectedFormat: "CSV",
    expectedFields: ["centre_name", "postal_code", "service_model"],
  },
  {
    sourceTool: "sg_msf_family_services",
    source: "MSF via data.gov.sg",
    datasetId: "d_add23c06f7267e799185c79ccaa2099b",
    reader: "geojson",
    expectedFormat: "GEOJSON",
    expectedFields: ["NAME", "ADDRESSPOSTALCODE", "FMEL_UPD_D"],
  },
  {
    sourceTool: "sg_msf_student_care_services",
    source: "MSF via data.gov.sg",
    datasetId: "d_77e6e0d58ce4743dab1f26dfcbbeb6f4",
    reader: "geojson",
    expectedFormat: "GEOJSON",
    expectedFields: ["NAME_OF_STUDENT_CARE_CENTRE", "SCC_POSTAL_CODE", "FMEL_UPD_D"],
  },
  {
    sourceTool: "sg_msf_social_service_offices",
    source: "MSF via data.gov.sg",
    datasetId: "d_22cfe2aed0bf20a679ab59bcaf0f8248",
    reader: "geojson",
    expectedFormat: "GEOJSON",
    expectedFields: ["NAME", "POSTALCODE", "FMEL_UPD_D"],
  },
  {
    sourceTool: "sg_moh_facilities",
    source: "MOH via data.gov.sg",
    datasetId: "d_548c33ea2d99e29ec63a7cc9edcccedc",
    reader: "geojson",
    expectedFormat: "GEOJSON",
    expectedFields: ["Description"],
  },
];

const pause = (milliseconds) => new Promise((resolvePause) => {
  setTimeout(resolvePause, milliseconds);
});

const escapeCell = (value) => String(value ?? "n/a").replaceAll("|", "\\|").replace(/\s+/g, " ").trim();

const classifyError = (error) => {
  const message = error instanceof Error ? error.message : String(error);
  if (/\b(rate limit|too many requests|429)\b/i.test(message)) return "gap";
  return "error";
};

const readSample = async (contract, client) => {
  if (contract.reader === "datastore") {
    const result = await client.getDatasetRows({ datasetId: contract.datasetId, limit: 1 });
    const fields = result.fields.map((field) => field.id);
    const rowFields = Object.keys(result.records[0] ?? {});
    return { recordCount: result.records.length, fields: [...new Set([...fields, ...rowFields])] };
  }

  if (contract.reader === "geojson") {
    const collection = await client.downloadDatasetGeoJson(contract.datasetId, "STATIC");
    const feature = collection.features[0];
    return {
      recordCount: collection.features.length,
      fields: Object.keys(feature?.properties ?? {}),
    };
  }

  if (contract.reader === "csv") {
    const rows = await client.downloadDatasetCsvRows(contract.datasetId, "STATIC");
    return { recordCount: rows.length, fields: Object.keys(rows[0] ?? {}) };
  }

  if (contract.reader === "xlsx") {
    const rows = await client.downloadDatasetXlsxRows(contract.datasetId, "STATIC");
    return { recordCount: rows.length, fields: Object.keys(rows[0] ?? {}) };
  }

  throw new Error(`Unsupported source-contract reader ${contract.reader}`);
};

const checkContract = async (contract, client) => {
  try {
    const metadata = await client.getDatasetMetadata(contract.datasetId);
    if (metadata === null) {
      return {
        ...contract,
        state: "gap",
        currentFormat: null,
        datasetName: null,
        managedByAgencyName: null,
        lastUpdatedAt: null,
        recordCount: 0,
        observedFields: [],
        missingFields: contract.expectedFields,
        gapCodes: ["METADATA_NOT_RETURNED"],
        gapMessages: ["data.gov.sg metadata returned no dataset record."],
      };
    }

    const sample = await readSample(contract, client);
    const observed = new Set(sample.fields);
    const missingFields = contract.expectedFields.filter((field) => !observed.has(field));
    const formatMatches = metadata.format.toUpperCase() === contract.expectedFormat;
    const state = formatMatches && missingFields.length === 0 && sample.recordCount > 0 ? "ready" : "gap";
    return {
      ...contract,
      state,
      currentFormat: metadata.format,
      datasetName: metadata.name,
      managedByAgencyName: metadata.managedByAgencyName,
      lastUpdatedAt: metadata.lastUpdatedAt,
      recordCount: sample.recordCount,
      observedFields: sample.fields,
      missingFields,
      gapCodes: [
        ...(formatMatches ? [] : ["FORMAT_DRIFT"]),
        ...(sample.recordCount > 0 ? [] : ["EMPTY_SAMPLE"]),
        ...(missingFields.length === 0 ? [] : ["FIELD_DRIFT"]),
      ],
      gapMessages: [
        ...(formatMatches ? [] : [`Expected ${contract.expectedFormat}, got ${metadata.format}.`]),
        ...(sample.recordCount > 0 ? [] : ["Sample read returned no source rows."]),
        ...(missingFields.length === 0 ? [] : [`Missing expected fields: ${missingFields.join(", ")}.`]),
      ],
    };
  } catch (error) {
    return {
      ...contract,
      state: classifyError(error),
      currentFormat: null,
      datasetName: null,
      managedByAgencyName: null,
      lastUpdatedAt: null,
      recordCount: 0,
      observedFields: [],
      missingFields: contract.expectedFields,
      gapCodes: ["SOURCE_CONTRACT_CHECK_FAILED"],
      gapMessages: [error instanceof Error ? error.message : String(error)],
    };
  }
};

const writeArtifacts = (artifact) => {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(artifact, null, 2) + "\n");

  mkdirSync(dirname(markdownPath), { recursive: true });
  const markdown = [
    "# Swee Source Contract Drift Benchmark",
    "",
    `Generated: ${artifact.generatedAt}`,
    "",
    "| Tool | Dataset | Reader | Format | State | Records | Gaps |",
    "| --- | --- | --- | --- | --- | ---: | --- |",
    ...artifact.contractChecks.map((check) =>
      `| ${escapeCell(check.sourceTool)} | ${escapeCell(check.datasetId)} | ${escapeCell(check.reader)} | ${escapeCell(check.currentFormat)} | ${escapeCell(check.state)} | ${check.recordCount} | ${escapeCell(check.gapCodes.join(", ") || "none")} |`,
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
  const stateDir = mkdtempSync(resolve(tmpdir(), "swee-source-contracts-"));
  const previousStateDir = process.env["SG_APIS_STATE_DIR"];
  process.env["SG_APIS_STATE_DIR"] = stateDir;
  try {
    const client = await import(pathToFileURL(resolve(root, "packages/mcp-server/dist/apis/datagov/client.js")).href);
    const contractChecks = [];
    for (const contract of CONTRACTS) {
      contractChecks.push(await checkContract(contract, client));
      if (contract.reader !== "datastore") {
        await pause(DATASET_DOWNLOAD_PAUSE_MS);
      }
    }
    const artifact = {
      schemaVersion: "swee-source-contracts-live-benchmark/v1",
      generatedAt,
      source: "local-live-datagov",
      command: "npm run benchmark:sources:contracts:live",
      contractChecks,
      limits: [
        "This artifact checks current source contracts only; it is not an SLA or official public-agency service status.",
        "Ready means metadata and a bounded sample matched the adapter's expected reader and fields during this run.",
        "Gaps and rate limits are reported directly; missing fields are not synthesized.",
      ],
    };
    writeArtifacts(artifact);
    process.stdout.write(`${JSON.stringify({
      ok: true,
      output: outputPath,
      markdown: markdownPath,
      states: Object.fromEntries(contractChecks.map((check) => [`${check.sourceTool}:${check.datasetId}`, check.state])),
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
  process.stderr.write("Run npm run build first. Source contract gaps should be written into the artifact instead of becoming invented source values.\n");
  process.exit(1);
});
