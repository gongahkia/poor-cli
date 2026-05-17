import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const catalogPath = resolve(root, "packages/mcp-server/dist/tools/catalog.js");
const opsTaxonomyPath = resolve(root, "packages/mcp-server/dist/ops-taxonomy.js");
const ownershipPath = resolve(root, "docs/ownership-matrix.json");

const requireFile = (filePath) => {
  if (!existsSync(filePath)) {
    throw new Error(`Missing required governance file: ${filePath}`);
  }
};

const ensureIncludes = (filePath, snippets) => {
  const text = readFileSync(filePath, "utf8");
  for (const snippet of snippets) {
    if (!text.includes(snippet)) {
      throw new Error(`${filePath} is missing required governance snippet: ${snippet}`);
    }
  }
};

const readJson = (filePath) => JSON.parse(readFileSync(filePath, "utf8"));

requireFile(catalogPath);
requireFile(opsTaxonomyPath);
requireFile(ownershipPath);
requireFile(resolve(root, "docs/governance-checklist.md"));
requireFile(resolve(root, "docs/deprecation-policy.md"));
requireFile(resolve(root, "docs/audit-retention-policy.md"));
requireFile(resolve(root, "docs/acra-licensing-track.md"));
requireFile(resolve(root, "docs/commercial-data-use.md"));
requireFile(resolve(root, "docs/privacy-dpo-readiness.md"));
requireFile(resolve(root, "docs/data-processing-agreement-template.md"));
requireFile(resolve(root, "docs/soc2-type1-roadmap.md"));
requireFile(resolve(root, "docs/mas-outsourcing-readiness.md"));
requireFile(resolve(root, "docs/npm-publish-readiness.md"));
requireFile(resolve(root, "docs/psg-application-track.md"));
requireFile(resolve(root, "docs/product/hosted-onboarding.md"));
requireFile(resolve(root, "docs/kpi-thresholds.md"));
requireFile(resolve(root, "config/kpi-thresholds.example.json"));
requireFile(resolve(root, "docs/quarterly-product-health-template.md"));
requireFile(resolve(root, "docs/release.md"));

const { API_CATALOG, WORKFLOW_CATALOG } = await import(pathToFileURL(catalogPath).href);
const { OPS_TAXONOMY_CATALOG } = await import(pathToFileURL(opsTaxonomyPath).href);
const matrix = readJson(ownershipPath);

const walkFiles = (dirPath) => {
  const files = [];
  for (const entry of readdirSync(dirPath, { withFileTypes: true })) {
    const entryPath = resolve(dirPath, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__tests__" || entry.name === "fixtures" || entry.name === "mock-server") {
        continue;
      }
      files.push(...walkFiles(entryPath));
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".ts")) {
      files.push(entryPath);
    }
  }
  return files;
};

const extractApiErrorCodes = (text) => {
  const emitted = new Set();
  const apiErrorPattern = /new ApiError\s*\(\s*\{([\s\S]*?)\}\s*\)/g;

  for (const match of text.matchAll(apiErrorPattern)) {
    const block = match[1] ?? "";
    const explicitCode = /code\s*:\s*"([A-Z0-9_]+)"/.exec(block)?.[1];
    if (explicitCode !== undefined) {
      emitted.add(explicitCode);
      continue;
    }

    const statusLiteral = /statusCode\s*:\s*(\d{3})/.exec(block)?.[1];
    if (statusLiteral !== undefined) {
      const numericStatus = Number.parseInt(statusLiteral, 10);
      if (numericStatus === 429) emitted.add("HTTP_429");
      else if (numericStatus >= 500) emitted.add("HTTP_5XX");
      else if (numericStatus >= 400) emitted.add("HTTP_4XX");
      continue;
    }

    if (/statusCode\s*:/.test(block)) {
      emitted.add("HTTP_4XX");
      emitted.add("HTTP_5XX");
    }
  }

  return emitted;
};

const extractManualStructuredErrorCodes = (text) => {
  const emitted = new Set();
  const errorObjectPattern = /structuredContent\s*:\s*\{[\s\S]*?error\s*:\s*\{([\s\S]*?)\}\s*,?\s*\}/g;
  for (const match of text.matchAll(errorObjectPattern)) {
    const block = match[1] ?? "";
    const code = /code\s*:\s*"([A-Z0-9_]+)"/.exec(block)?.[1];
    if (code !== undefined) {
      emitted.add(code);
    }
  }
  return emitted;
};

const collectEmittedToolErrorCodes = () => {
  const emitted = new Set([
    "VALIDATION_ERROR",
    "INTERNAL_ERROR",
    "TOOL_RESULT_ERROR",
    "WORKFLOW_DEPENDENCY_ERROR",
  ]);

  const scanRoots = [
    resolve(root, "packages/shared/src/http-client.ts"),
    resolve(root, "packages/mcp-server/src/router/planner.ts"),
    resolve(root, "packages/mcp-server/src/tools/query/rendering.ts"),
    resolve(root, "packages/mcp-server/src/tools/transit-intelligence-tools.ts"),
    resolve(root, "packages/mcp-server/src/tools/trace-tools.ts"),
    resolve(root, "packages/mcp-server/src/apis"),
  ];

  for (const scanRoot of scanRoots) {
    const candidates = statSync(scanRoot).isDirectory() ? walkFiles(scanRoot) : [scanRoot];
    for (const filePath of candidates) {
      const text = readFileSync(filePath, "utf8");
      for (const code of extractApiErrorCodes(text)) {
        emitted.add(code);
      }
      for (const code of extractManualStructuredErrorCodes(text)) {
        emitted.add(code);
      }
    }
  }

  return emitted;
};

if (!Array.isArray(matrix.apiFamilies) || !Array.isArray(matrix.workflows)) {
  throw new Error("docs/ownership-matrix.json must define apiFamilies[] and workflows[] arrays.");
}

const familiesByName = new Map(matrix.apiFamilies.map((entry) => [entry.name, entry]));
for (const family of API_CATALOG) {
  const owned = familiesByName.get(family.name);
  if (owned === undefined) {
    throw new Error(`Ownership matrix is missing API family owner: ${family.name}`);
  }
  if (typeof owned.primaryOwner !== "string" || owned.primaryOwner.trim() === "") {
    throw new Error(`API family ${family.name} is missing primaryOwner.`);
  }
  if (typeof owned.backupOwner !== "string" || owned.backupOwner.trim() === "") {
    throw new Error(`API family ${family.name} is missing backupOwner.`);
  }
}

const workflowsByName = new Map(matrix.workflows.map((entry) => [entry.name, entry]));
for (const workflow of WORKFLOW_CATALOG) {
  const owned = workflowsByName.get(workflow.name);
  if (owned === undefined) {
    throw new Error(`Ownership matrix is missing workflow owner: ${workflow.name}`);
  }
  if (typeof owned.primaryOwner !== "string" || owned.primaryOwner.trim() === "") {
    throw new Error(`Workflow ${workflow.name} is missing primaryOwner.`);
  }
  if (typeof owned.backupOwner !== "string" || owned.backupOwner.trim() === "") {
    throw new Error(`Workflow ${workflow.name} is missing backupOwner.`);
  }
}

ensureIncludes(resolve(root, "docs/governance-checklist.md"), [
  "npm run release:preflight",
  "No new API family without a documented use case, maintainer owner, and test plan.",
  "No release without passing verify, smoke, and policy checks.",
  "KPI dashboard evidence snapshots",
]);

ensureIncludes(resolve(root, "docs/deprecation-policy.md"), [
  "migration path",
  "Deprecation Notice",
  "Migration Mapping Template",
]);

ensureIncludes(resolve(root, "docs/audit-retention-policy.md"), [
  "SG_APIS_AUDIT_MAX_ENTRIES",
  "SG_APIS_AUDIT_RETENTION_SEC",
  "traceId",
  "requestId",
]);

ensureIncludes(resolve(root, "docs/acra-licensing-track.md"), [
  "ACRA API Marketplace",
  "Authorised ISP Shortlist",
  "Release Blocker",
  "sourceUseWarnings",
  "CRIF BizInsights",
  "DC Frontiers Pte. Ltd. (Handshakes)",
  "Experian Credit Services Singapore Pte. Ltd.",
  "Singapore Commercial Credit Bureau Pte. Ltd.",
]);

ensureIncludes(resolve(root, "docs/commercial-data-use.md"), [
  "ACRA",
  "OneMap",
  "URA",
  "sourceUseWarnings",
  "Singapore Open Data Licence",
  "Developer Agreement",
]);

ensureIncludes(resolve(root, "docs/privacy-dpo-readiness.md"), [
  "PDPA Notification Language",
  "DPO Appointment And Contact Surface",
  "Privacy Notice Skeleton",
  "Retention Summary",
  "DPIA Checklist Before Hosted Beta",
]);

ensureIncludes(resolve(root, "docs/data-processing-agreement-template.md"), [
  "Data-Intermediary Obligations",
  "Subprocessors",
  "Retention, Return, And Deletion",
  "Security Incident And Breach Notification",
  "Audit Cooperation",
  "Legal Review Gate",
]);

ensureIncludes(resolve(root, "docs/soc2-type1-roadmap.md"), [
  "Readiness Gap Analysis",
  "Build-Vs-Tool Path",
  "Control Backlog",
  "Cost And Buyer Trigger",
  "AICPA",
]);

ensureIncludes(resolve(root, "docs/mas-outsourcing-readiness.md"), [
  "Business Continuity And Operational Resilience",
  "Incident Response",
  "Subprocessors And Subcontracting",
  "Data Residency And Customer Information",
  "Required Controls Before FI-Adjacent Sales",
  "Data Processing Agreement template",
  "soc2-type1-roadmap.md",
]);

ensureIncludes(resolve(root, "docs/npm-publish-readiness.md"), [
  "@dude/mcp",
  "npm run release:dryrun",
  "npm publish --workspace packages/mcp-server --access public --dry-run",
  "NPM_TOKEN",
  "npm view @dude/mcp version",
]);

ensureIncludes(resolve(root, "docs/psg-application-track.md"), [
  "EnterpriseSG Productivity Solutions Grant",
  "IMDA Pre-Approval Onboarding Guide",
  "five qualifying SME customers",
  "Vendor Management Portal",
  "Do not claim Dude is PSG pre-approved",
]);

ensureIncludes(resolve(root, "docs/product/hosted-onboarding.md"), [
  "Data Processing Agreement template",
  "PDPA notification and DPO readiness pack",
  "SOC 2 Type I readiness roadmap",
  "MAS outsourcing readiness pack",
  "Commercial data use review",
]);

ensureIncludes(resolve(root, "docs/kpi-thresholds.md"), [
  "SG_APIS_KPI_THRESHOLDS_PATH",
  "overallPolicyStatus",
  "allow-kpi-breach",
]);

ensureIncludes(resolve(root, "docs/quarterly-product-health-template.md"), [
  "KPI Summary",
  "Reliability And Security",
  "Adoption And Ecosystem",
  "Governance And Ownership",
]);

ensureIncludes(resolve(root, "docs/release.md"), [
  "Governance Checklist",
  "node ./scripts/check-governance.mjs",
  "npm run release:preflight",
  "npm run kpis:dashboard",
  "npm run release:evidence",
  "npm run quarterly:report",
  "allow-kpi-breach",
]);

if (!Array.isArray(OPS_TAXONOMY_CATALOG.errorCodes)) {
  throw new Error("OPS_TAXONOMY_CATALOG.errorCodes must be present.");
}

const taxonomyCodes = new Set(
  OPS_TAXONOMY_CATALOG.errorCodes
    .map((entry) => entry?.code)
    .filter((code) => typeof code === "string"),
);
const emittedErrorCodes = collectEmittedToolErrorCodes();
const missingTaxonomy = [...emittedErrorCodes].filter((code) => !taxonomyCodes.has(code)).sort();
if (missingTaxonomy.length > 0) {
  throw new Error(`Ops taxonomy is missing emitted tool-error code(s): ${missingTaxonomy.join(", ")}`);
}

process.stdout.write(
  `Governance policy OK: ${API_CATALOG.length} API families, ${WORKFLOW_CATALOG.length} workflows, and ${emittedErrorCodes.size} emitted error codes have explicit governance coverage.\n`,
);
