import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const rulesPath = resolve(root, "packages/mcp-server/src/housing/rules-2026.json");

const STALE_AFTER_DAYS = 365;
const POST_BUDGET_GRACE_DAYS = 60; // SG Budget is delivered ~Feb; allow ~Mar/early-Apr to refresh

const parseDate = (value) => {
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) {
    throw new Error(`Invalid date in rules file: ${value}`);
  }
  return new Date(ms);
};

const daysBetween = (a, b) => Math.floor((b.getTime() - a.getTime()) / (24 * 60 * 60 * 1000));

const mostRecentBudgetDate = (now) => {
  // SG Budget is delivered in mid-Feb each year; treat 2026-02-15 as the canonical anchor.
  const year = now.getUTCMonth() < 1 || (now.getUTCMonth() === 1 && now.getUTCDate() < 15)
    ? now.getUTCFullYear() - 1
    : now.getUTCFullYear();
  return new Date(Date.UTC(year, 1, 15));
};

const main = () => {
  const text = readFileSync(rulesPath, "utf8");
  const rules = JSON.parse(text);
  const now = new Date();
  const lastVerified = parseDate(rules.lastVerified);
  const ageDays = daysBetween(lastVerified, now);
  const budgetDate = mostRecentBudgetDate(now);
  const postBudget = now.getTime() > budgetDate.getTime() + POST_BUDGET_GRACE_DAYS * 24 * 60 * 60 * 1000;
  const verifiedSinceBudget = lastVerified.getTime() >= budgetDate.getTime();

  const warnings = [];
  if (ageDays > STALE_AFTER_DAYS) {
    warnings.push(`Housing rules lastVerified is ${ageDays} days old (threshold ${STALE_AFTER_DAYS}). Refresh before relying on grant/loan/affordability outputs.`);
  }
  if (postBudget && !verifiedSinceBudget) {
    warnings.push(`Housing rules have not been re-verified since the most recent SG Budget (${budgetDate.toISOString().slice(0, 10)}). Confirm grant ceilings, MSR/TDSR/LTV, and BSD tiers against current sources.`);
  }

  const unverified = rules?.verificationLog?.[rules.lastVerified]?.unverifiedFields ?? [];
  if (Array.isArray(unverified) && unverified.length > 0) {
    warnings.push(`${unverified.length} field(s) flagged unverified in the latest verification log entry: ${unverified.slice(0, 3).join("; ")}${unverified.length > 3 ? "; ..." : ""}`);
  }

  if (warnings.length === 0) {
    process.stdout.write(`Housing rules freshness ok. version=${rules.version} lastVerified=${rules.lastVerified} ageDays=${ageDays}\n`);
    return;
  }

  process.stderr.write(`Housing rules freshness warning(s):\n`);
  for (const warning of warnings) {
    process.stderr.write(`- ${warning}\n`);
  }

  if (process.env.SG_APIS_HOUSING_RULES_STRICT === "1") {
    process.exit(1);
  }
};

main();
