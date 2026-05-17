import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  SG_RISK_RULE_CODES,
  SG_RISK_RULES_LAST_REVIEWED,
  SG_RISK_RULES_SCHEMA_VERSION,
  SG_RISK_RULES_VERSION,
} from "../risk-rules.js";

const here = dirname(fileURLToPath(import.meta.url));
const rulesPath = resolve(here, "../../../../../rules/sg-risk-rules.yml");
const rulesYaml = readFileSync(rulesPath, "utf8");

describe("Singapore risk rules pack", () => {
  it("publishes the expected schema and version metadata", () => {
    expect(rulesYaml).toContain(`schemaVersion: ${SG_RISK_RULES_SCHEMA_VERSION}`);
    expect(rulesYaml).toContain(`version: ${SG_RISK_RULES_VERSION}`);
    expect(rulesYaml).toContain(`lastReviewed: ${SG_RISK_RULES_LAST_REVIEWED}`);
  });

  it("documents every runtime risk code with severity, requirements, and success evidence", () => {
    for (const code of SG_RISK_RULE_CODES) {
      const start = rulesYaml.indexOf(`id: ${code}`);
      expect(start, `${code} should exist in rules YAML`).toBeGreaterThan(-1);
      const nextRule = rulesYaml.indexOf("\n  - id:", start + 1);
      const block = rulesYaml.slice(start, nextRule === -1 ? undefined : nextRule);

      expect(block, `${code} should declare severity`).toMatch(/severity: (high|medium|low)/);
      expect(block, `${code} should declare data requirements`).toContain("dataRequirements:");
      expect(block, `${code} should declare success evidence`).toContain("successEvidence:");
    }
  });
});
