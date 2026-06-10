import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

const targets = [
  "README.md",
  "architecture_diagram.md",
  "docs/submission/significant-update.md",
  "docs/submission/demo-script.md",
];

const negated = /\b(no|not|never|without|does not|do not|must not|forbidden|gated|unverified)\b/i;
const rules = [
  {
    id: "deterministic_replay",
    pattern: /\bdeterministic replay\b/i,
    allowed: negated,
  },
  {
    id: "splunk_cannot_sanitize",
    pattern: /\bSplunk (?:cannot|can't|can not) sanitize\b/i,
    allowed: negated,
  },
  {
    id: "live_auth_claim",
    pattern: /\b(?:proves?|confirms?|verifies?)\b.*\blive Splunk auth\b|\blive Splunk auth\b.*\b(?:works?|verified|confirmed)\b/i,
    allowed: negated,
  },
  {
    id: "synthetic_is_live",
    pattern: /\bsynthetic\b.*\blive Splunk\b|\blive Splunk\b.*\bsynthetic\b/i,
    allowed: negated,
  },
  {
    id: "raw_output_storage",
    pattern: /\b(full raw Splunk output storage|stores? raw Splunk output|raw Splunk output is stored)\b/i,
    allowed: negated,
  },
  {
    id: "guaranteed_prevention",
    pattern: /\bguarantee(?:d|s)?\b.*\b(prompt injection|data leakage|leakage|leak|exfiltration)\b/i,
    allowed: negated,
  },
  {
    id: "missing_evidence_clearance",
    pattern: /\bmissing Splunk evidence\b.*\b(safe|clean|compliant|clearance|risk-free)\b/i,
    allowed: negated,
  },
];

const failures = [];

for (const file of targets) {
  const text = readFileSync(resolve(root, file), "utf8");
  const lines = text.split(/\r?\n/);
  for (const [index, line] of lines.entries()) {
    for (const rule of rules) {
      if (rule.pattern.test(line) && !rule.allowed.test(line)) {
        failures.push(`${file}:${index + 1}: ${rule.id}: ${line.trim()}`);
      }
    }
  }
}

if (failures.length > 0) {
  process.stderr.write("Submission claims guard failed:\n");
  for (const failure of failures) process.stderr.write(`- ${failure}\n`);
  process.exit(1);
}

process.stdout.write("submission claims guard passed\n");
