import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const allowlistPath = resolve(
  root,
  process.env.DUDE_NPM_AUDIT_ALLOWLIST ?? "config/npm-audit-allowlist.json",
);

const severityRank = {
  info: 0,
  low: 1,
  moderate: 2,
  high: 3,
  critical: 4,
};

const trackedSeverities = new Set(["moderate", "high", "critical"]);

const readAllowlist = () => {
  const parsed = JSON.parse(readFileSync(allowlistPath, "utf8"));
  const entries = Array.isArray(parsed.allowlist) ? parsed.allowlist : [];
  const invalid = entries.filter((entry) => {
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
      return true;
    }
    const record = entry;
    const packageName = typeof record.package === "string" ? record.package.trim() : "";
    const rationale = typeof record.rationale === "string" ? record.rationale.trim() : "";
    const tracking = typeof record.tracking === "string" ? record.tracking.trim() : "";
    const advisoryId = typeof record.advisoryId === "string" ? record.advisoryId.trim() : "";
    const title = typeof record.title === "string" ? record.title.trim() : "";
    const severity = typeof record.severity === "string" ? record.severity.trim().toLowerCase() : "";
    return packageName === ""
      || rationale === ""
      || tracking === ""
      || (advisoryId === "" && title === "")
      || !trackedSeverities.has(severity);
  });

  if (invalid.length > 0) {
    throw new Error(
      `${allowlistPath} has ${invalid.length} invalid entr${invalid.length === 1 ? "y" : "ies"}. `
        + "Each entry needs package, severity, advisoryId or title, rationale, and tracking.",
    );
  }

  return entries.map((entry) => ({
    advisoryId: typeof entry.advisoryId === "string" ? entry.advisoryId.trim() : undefined,
    package: entry.package.trim(),
    rationale: entry.rationale.trim(),
    severity: entry.severity.trim().toLowerCase(),
    title: typeof entry.title === "string" ? entry.title.trim() : undefined,
    tracking: entry.tracking.trim(),
  }));
};

const runAudit = () => {
  const result = spawnSync("npm", ["audit", "--omit=dev", "--json"], {
    cwd: root,
    encoding: "utf8",
    env: process.env,
    maxBuffer: 20 * 1024 * 1024,
  });

  if (result.error !== undefined) {
    throw result.error;
  }

  const output = result.stdout.trim() !== "" ? result.stdout : result.stderr;
  if (output.trim() === "") {
    throw new Error("npm audit produced no JSON output.");
  }

  return JSON.parse(output);
};

const normalizeVia = (via) => {
  if (!Array.isArray(via)) {
    return [];
  }
  return via
    .filter((item) => item !== null && typeof item === "object" && !Array.isArray(item))
    .map((item) => ({
      advisoryId: item.source === undefined ? undefined : String(item.source),
      dependency: typeof item.dependency === "string" ? item.dependency : undefined,
      severity: typeof item.severity === "string" ? item.severity.toLowerCase() : undefined,
      title: typeof item.title === "string" ? item.title : undefined,
      url: typeof item.url === "string" ? item.url : undefined,
    }));
};

const collectFindings = (auditReport) => {
  const vulnerabilities = auditReport?.vulnerabilities;
  if (vulnerabilities === null || typeof vulnerabilities !== "object" || Array.isArray(vulnerabilities)) {
    return [];
  }

  return Object.entries(vulnerabilities).flatMap(([packageName, vulnerability]) => {
    if (vulnerability === null || typeof vulnerability !== "object" || Array.isArray(vulnerability)) {
      return [];
    }
    const severity = typeof vulnerability.severity === "string"
      ? vulnerability.severity.toLowerCase()
      : "info";
    if ((severityRank[severity] ?? 0) < severityRank.moderate) {
      return [];
    }

    const advisories = normalizeVia(vulnerability.via);
    if (advisories.length === 0) {
      return [{
        advisoryId: `${packageName}:${severity}`,
        package: packageName,
        severity,
        title: `${packageName} ${severity} vulnerability`,
        url: undefined,
      }];
    }

    return advisories.map((advisory) => ({
      advisoryId: advisory.advisoryId ?? `${packageName}:${advisory.title ?? severity}`,
      package: advisory.dependency ?? packageName,
      severity: advisory.severity ?? severity,
      title: advisory.title ?? `${packageName} ${severity} vulnerability`,
      url: advisory.url,
    }));
  });
};

const isAllowlisted = (finding, allowlist) =>
  allowlist.some((entry) => {
    const severityMatches = severityRank[entry.severity] >= severityRank[finding.severity];
    const advisoryMatches = entry.advisoryId !== undefined && entry.advisoryId === finding.advisoryId;
    const titleMatches = entry.title !== undefined && entry.title === finding.title;
    return entry.package === finding.package && severityMatches && (advisoryMatches || titleMatches);
  });

const main = () => {
  const allowlist = readAllowlist();
  const auditReport = runAudit();
  const findings = collectFindings(auditReport);
  const untracked = findings.filter((finding) => !isAllowlisted(finding, allowlist));
  const allowlisted = findings.length - untracked.length;

  if (untracked.length > 0) {
    process.stderr.write("Production npm audit gate failed.\n");
    for (const finding of untracked) {
      process.stderr.write(
        `- ${finding.severity.toUpperCase()} ${finding.package}: ${finding.title} `
          + `(advisoryId: ${finding.advisoryId})${finding.url === undefined ? "" : ` ${finding.url}`}\n`,
      );
    }
    process.stderr.write(
      "\nHigh/critical findings must be fixed or allowlisted with rationale. "
        + "Moderate findings need a tracking entry or explicit allowlist entry.\n",
    );
    process.exit(1);
  }

  process.stdout.write(
    `Production npm audit gate passed: ${findings.length} moderate/high/critical finding`
      + `${findings.length === 1 ? "" : "s"} (${allowlisted} allowlisted).\n`,
  );
};

try {
  main();
} catch (error) {
  process.stderr.write(`Production npm audit gate failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
}
