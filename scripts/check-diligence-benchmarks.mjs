import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const benchmarkPath = resolve(root, "benchmarks/diligence-edge-cases.json");
const payload = JSON.parse(readFileSync(benchmarkPath, "utf8"));

const fail = (message) => {
  process.stderr.write(`diligence benchmark check failed: ${message}\n`);
  process.exit(1);
};

if (payload.schemaVersion !== "diligence-edge-cases/v1") {
  fail("schemaVersion must be diligence-edge-cases/v1");
}

if (!Array.isArray(payload.legalEthicalCriteria) || payload.legalEthicalCriteria.length < 5) {
  fail("legalEthicalCriteria must include at least five criteria");
}

if (!Array.isArray(payload.falsePositiveLimitations) || payload.falsePositiveLimitations.length === 0) {
  fail("falsePositiveLimitations must be documented");
}

if (!Array.isArray(payload.falseNegativeLimitations) || payload.falseNegativeLimitations.length === 0) {
  fail("falseNegativeLimitations must be documented");
}

if (!Array.isArray(payload.cases) || payload.cases.length !== 50) {
  fail(`expected exactly 50 cases, found ${Array.isArray(payload.cases) ? payload.cases.length : "non-array"}`);
}

const ids = new Set();
for (const [index, fixture] of payload.cases.entries()) {
  const label = `case ${index + 1}`;
  if (typeof fixture.id !== "string" || !/^bd-\d{3}$/.test(fixture.id)) {
    fail(`${label} must have a bd-### id`);
  }
  if (ids.has(fixture.id)) {
    fail(`${fixture.id} is duplicated`);
  }
  ids.add(fixture.id);

  for (const field of ["title", "falsePositiveNotes", "falseNegativeNotes"]) {
    if (typeof fixture[field] !== "string" || fixture[field].trim() === "") {
      fail(`${fixture.id} must include ${field}`);
    }
  }

  if (fixture.input === null || typeof fixture.input !== "object" || Array.isArray(fixture.input)) {
    fail(`${fixture.id} must include structured input`);
  }

  for (const field of ["expectedEvidence", "expectedGaps", "expectedLimits"]) {
    if (!Array.isArray(fixture[field])) {
      fail(`${fixture.id} must include ${field} array`);
    }
  }

  if (fixture.expectedEvidence.length === 0) {
    fail(`${fixture.id} must include at least one expected evidence assertion`);
  }
  if (fixture.expectedLimits.length === 0) {
    fail(`${fixture.id} must include at least one expected limit assertion`);
  }
}

process.stdout.write(`diligence benchmark fixtures ok: ${payload.cases.length} cases\n`);
