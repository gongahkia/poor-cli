#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { accessSync, constants, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const distCatalogPath = resolve(root, "packages/mcp-server/dist/tools/catalog.js");

const DEFAULT_OUTPUT_PATH = resolve(root, "artifacts/ecosystem/latest.json");
const DEFAULT_HISTORY_DIR = resolve(root, "artifacts/ecosystem/history");
const REQUEST_TIMEOUT_MS = 20000;

const GITHUB_REPOSITORIES = [
  "modelcontextprotocol/servers",
  "github/github-mcp-server",
  "hithereiamaliff/mcp-grabmaps",
  "sypherin/sgdata-mcp",
  "coolMukul/sg-property-mcp",
  "leejaew/sg-mrt-exits-mcp",
  "vdineshk/sg-data-mcp",
];

const NPM_PACKAGES = [
  "@altronis/sgdata-mcp",
  "sg-property-mcp",
  "@swee-sg/shield",
];

const STACKOVERFLOW_TAG = "model-context-protocol";

const parseArgs = (argv) => {
  const parsed = {
    output: DEFAULT_OUTPUT_PATH,
    historyDir: DEFAULT_HISTORY_DIR,
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--output") {
      const value = argv[index + 1];
      if (value === undefined) {
        throw new Error("Missing value for --output");
      }
      parsed.output = resolve(root, value);
      index++;
      continue;
    }
    if (arg === "--history-dir") {
      const value = argv[index + 1];
      if (value === undefined) {
        throw new Error("Missing value for --history-dir");
      }
      parsed.historyDir = resolve(root, value);
      index++;
      continue;
    }
  }

  return parsed;
};

const safeReadJson = (filePath) => {
  if (!existsSync(filePath)) {
    return null;
  }

  try {
    const raw = readFileSync(filePath, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

const toHistoryFilename = (isoTimestamp) => {
  const compact = isoTimestamp.replace(/[:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return `${compact}.json`;
};

const listFiles = (directory, extension) => {
  const results = [];
  const stack = [directory];

  while (stack.length > 0) {
    const current = stack.pop();
    if (current === undefined) {
      continue;
    }

    const entries = readdirSync(current);
    for (const entry of entries) {
      const fullPath = resolve(current, entry);
      const stats = statSync(fullPath);
      if (stats.isDirectory()) {
        stack.push(fullPath);
        continue;
      }
      if (fullPath.endsWith(extension)) {
        results.push(fullPath);
      }
    }
  }

  return results;
};

const gitValue = (args) => {
  try {
    return execFileSync("git", args, {
      cwd: root,
      encoding: "utf8",
    }).trim();
  } catch {
    return null;
  }
};

const fetchJson = async (url, headers = {}) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        "User-Agent": "swee-sg-ecosystem-snapshot",
        ...headers,
      },
      signal: controller.signal,
    });
    const text = await response.text();
    const parsed = text === "" ? null : JSON.parse(text);
    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: parsed,
      };
    }
    return {
      ok: true,
      status: response.status,
      data: parsed,
    };
  } catch (error) {
    return {
      ok: false,
      status: null,
      error: error instanceof Error ? error.message : String(error),
    };
  } finally {
    clearTimeout(timer);
  }
};

const summarizeGitHubRepo = (payload) => ({
  fullName: payload.full_name,
  description: payload.description,
  stars: payload.stargazers_count,
  forks: payload.forks_count,
  openIssues: payload.open_issues_count,
  watchers: payload.subscribers_count ?? payload.watchers_count,
  language: payload.language,
  license: payload.license?.spdx_id ?? null,
  createdAt: payload.created_at,
  pushedAt: payload.pushed_at,
  updatedAt: payload.updated_at,
  htmlUrl: payload.html_url,
});

const summarizeNpmPackage = (packageName, registryPayload, downloadsPayload) => {
  if (registryPayload.ok !== true) {
    return {
      packageName,
      found: false,
      downloadsLastMonth: downloadsPayload.ok === true ? downloadsPayload.data.downloads ?? null : null,
      error: registryPayload.error,
    };
  }

  return {
    packageName,
    found: true,
    latestVersion: registryPayload.data?.["dist-tags"]?.latest ?? null,
    createdAt: registryPayload.data?.time?.created ?? null,
    modifiedAt: registryPayload.data?.time?.modified ?? null,
    downloadsLastMonth: downloadsPayload.ok === true ? downloadsPayload.data.downloads ?? null : null,
  };
};

const collectToolTestCoverage = (toolNames) => {
  const testDirectories = [
    resolve(root, "packages/mcp-server/src/__tests__"),
    resolve(root, "packages/mcp-server/src/tools/__tests__"),
    resolve(root, "packages/shared/src/__tests__"),
  ];

  const testFiles = testDirectories.flatMap((directory) => listFiles(directory, ".ts"));
  const testContents = new Map(testFiles.map((filePath) => [filePath, readFileSync(filePath, "utf8")]));

  const referenceCounts = toolNames.map((toolName) => {
    let count = 0;
    for (const content of testContents.values()) {
      if (content.includes(toolName)) {
        count += 1;
      }
    }
    return {
      toolName,
      testFileReferences: count,
    };
  });

  referenceCounts.sort((left, right) => right.testFileReferences - left.testFileReferences || left.toolName.localeCompare(right.toolName));

  return {
    totalTestFiles: testFiles.length,
    toolsWithoutDirectTestReference: referenceCounts.filter((entry) => entry.testFileReferences === 0).map((entry) => entry.toolName),
    topReferencedTools: referenceCounts.slice(0, 20),
  };
};

const main = async () => {
  const args = parseArgs(process.argv.slice(2));
  const previousSnapshot = safeReadJson(args.output);

  try {
    accessSync(distCatalogPath, constants.R_OK);
  } catch {
    throw new Error("Missing built catalog. Run `npm run build` before generating the ecosystem snapshot.");
  }

  const {
    API_CATALOG,
    RECIPE_CATALOG,
    RESOURCE_URIS,
    TOOL_CATALOG,
    WORKFLOW_CATALOG,
  } = await import(pathToFileURL(distCatalogPath).href);

  const githubToken = process.env.GITHUB_TOKEN;
  const githubHeaders = githubToken === undefined
    ? {}
    : { Authorization: `Bearer ${githubToken}` };

  const [githubRepoResults, npmPackageResults, stackoverflowTagResult, stackoverflowLatestQuestionsResult, stackoverflowTopQuestionsResult, githubSearchResult] = await Promise.all([
    Promise.all(GITHUB_REPOSITORIES.map(async (repo) => {
      const result = await fetchJson(`https://api.github.com/repos/${repo}`, githubHeaders);
      return {
        repo,
        ...(result.ok === true
          ? { found: true, metrics: summarizeGitHubRepo(result.data) }
          : { found: false, error: result.error }),
      };
    })),
    Promise.all(NPM_PACKAGES.map(async (packageName) => {
      const [registry, downloads] = await Promise.all([
        fetchJson(`https://registry.npmjs.org/${encodeURIComponent(packageName)}`),
        fetchJson(`https://api.npmjs.org/downloads/point/last-month/${encodeURIComponent(packageName)}`),
      ]);
      return summarizeNpmPackage(packageName, registry, downloads);
    })),
    fetchJson(`https://api.stackexchange.com/2.3/tags/${encodeURIComponent(STACKOVERFLOW_TAG)}/info?site=stackoverflow`),
    fetchJson(`https://api.stackexchange.com/2.3/questions?order=desc&sort=creation&tagged=${encodeURIComponent(STACKOVERFLOW_TAG)}&site=stackoverflow&pagesize=20`),
    fetchJson(`https://api.stackexchange.com/2.3/questions?order=desc&sort=votes&tagged=${encodeURIComponent(STACKOVERFLOW_TAG)}&site=stackoverflow&pagesize=20`),
    fetchJson("https://api.github.com/search/repositories?q=mcp+singapore+in:name,description&sort=updated&order=desc&per_page=20", githubHeaders),
  ]);

  const pulseTools = TOOL_CATALOG
    .filter((entry) => entry.name.startsWith("swee_pulse_"))
    .map((entry) => entry.name);
  const pulseFamilyCount = API_CATALOG
    .filter((entry) => entry.preferredInterface?.startsWith("swee_pulse_"))
    .length;

  const toolCoverage = collectToolTestCoverage(TOOL_CATALOG.map((entry) => entry.name));

  const stackoverflowTagInfo = stackoverflowTagResult.ok === true
    ? (stackoverflowTagResult.data.items?.[0] ?? null)
    : null;

  const mapQuestion = (question) => ({
    title: question.title,
    score: question.score,
    answerCount: question.answer_count,
    viewCount: question.view_count,
    createdAt: new Date(question.creation_date * 1000).toISOString(),
    link: question.link,
    tags: question.tags,
  });

  const generatedAt = new Date().toISOString();
  const snapshot = {
    schemaVersion: "1.0",
    generatedAt,
    repository: {
      path: root,
      branch: gitValue(["branch", "--show-current"]),
      commitSha: gitValue(["rev-parse", "HEAD"]),
      commitShortSha: gitValue(["rev-parse", "--short", "HEAD"]),
      nodeVersion: process.version,
    },
    localSurface: {
      toolCount: TOOL_CATALOG.length,
      apiFamilyCount: API_CATALOG.length,
      workflowCount: WORKFLOW_CATALOG.length,
      recipeCount: RECIPE_CATALOG.length,
      pulseFamilyCount,
      pulseTools,
      toolCatalogResources: RESOURCE_URIS,
      testCoverage: toolCoverage,
    },
    externalSignals: {
      githubRepositories: githubRepoResults,
      npmPackages: npmPackageResults,
      stackoverflow: {
        tag: STACKOVERFLOW_TAG,
        tagInfo: stackoverflowTagInfo === null
          ? {
            found: false,
            error: stackoverflowTagResult.ok ? "missing_tag_info" : stackoverflowTagResult.error,
          }
          : {
            found: true,
            questionCount: stackoverflowTagInfo.count,
            hasSynonyms: stackoverflowTagInfo.has_synonyms,
          },
        latestQuestions: stackoverflowLatestQuestionsResult.ok === true
          ? (stackoverflowLatestQuestionsResult.data.items ?? []).map(mapQuestion)
          : [],
        topQuestionsByVotes: stackoverflowTopQuestionsResult.ok === true
          ? (stackoverflowTopQuestionsResult.data.items ?? []).map(mapQuestion)
          : [],
      },
      singaporeMcpSearch: githubSearchResult.ok === true
        ? {
          totalCount: githubSearchResult.data.total_count,
          topRepositories: (githubSearchResult.data.items ?? []).map((repo) => ({
            fullName: repo.full_name,
            stars: repo.stargazers_count,
            forks: repo.forks_count,
            updatedAt: repo.updated_at,
            language: repo.language,
            htmlUrl: repo.html_url,
          })),
        }
        : {
          totalCount: null,
          topRepositories: [],
          error: githubSearchResult.error,
        },
    },
    sourceLinks: {
      mcpSpecTools: "https://modelcontextprotocol.io/specification/2025-06-18/server/tools",
      githubToolsetsGuidance: "https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/configure-toolsets",
      dataGovApiOverview: "https://guide.data.gov.sg/developer-guide/api-overview",
      dataGovRateLimits: "https://guide.data.gov.sg/developer-guide/api-overview/api-rate-limits",
      oneMapApiTerms: "https://www.onemap.gov.sg/legal/apitermsofservice.html",
      ltaDatamall: "https://datamall.lta.gov.sg/content/datamall/en.html",
      stackoverflowMcpTag: "https://stackoverflow.com/tags/model-context-protocol/info",
    },
    trendComparedToPrevious: previousSnapshot === null
      ? null
      : {
        previousGeneratedAt: typeof previousSnapshot.generatedAt === "string"
          ? previousSnapshot.generatedAt
          : null,
        delta: {
          toolCount: TOOL_CATALOG.length - Number(previousSnapshot.localSurface?.toolCount ?? TOOL_CATALOG.length),
          apiFamilyCount: API_CATALOG.length - Number(previousSnapshot.localSurface?.apiFamilyCount ?? API_CATALOG.length),
          workflowCount: WORKFLOW_CATALOG.length - Number(previousSnapshot.localSurface?.workflowCount ?? WORKFLOW_CATALOG.length),
          recipeCount: RECIPE_CATALOG.length - Number(previousSnapshot.localSurface?.recipeCount ?? RECIPE_CATALOG.length),
          pulseFamilyCount: pulseFamilyCount
            - Number(previousSnapshot.localSurface?.pulseFamilyCount ?? pulseFamilyCount),
        },
      },
  };

  mkdirSync(dirname(args.output), { recursive: true });
  writeFileSync(args.output, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  mkdirSync(args.historyDir, { recursive: true });
  const historyPath = resolve(args.historyDir, toHistoryFilename(generatedAt));
  writeFileSync(historyPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");

  process.stdout.write(`ecosystem snapshot written to ${args.output}\n`);
  process.stdout.write(`ecosystem history snapshot written to ${historyPath}\n`);
  process.stdout.write(`${JSON.stringify({
    generatedAt: snapshot.generatedAt,
    tools: snapshot.localSurface.toolCount,
    apiFamilies: snapshot.localSurface.apiFamilyCount,
    trackedGithubRepos: githubRepoResults.length,
    trackedNpmPackages: npmPackageResults.length,
    stackoverflowQuestionCount: snapshot.externalSignals.stackoverflow.tagInfo.found
      ? snapshot.externalSignals.stackoverflow.tagInfo.questionCount
      : null,
  }, null, 2)}\n`);
};

main().catch((error) => {
  process.stderr.write(`ecosystem snapshot failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
