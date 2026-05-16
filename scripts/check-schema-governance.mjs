import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

const read = (path) => readFileSync(resolve(root, path), "utf8");

const requiredContractIds = [
  "brief-envelope/v1",
  "business-dossier/v1",
  "country-pack/v1",
];

const requiredChangelogSections = [
  "Schema Changes",
  "Breaking Changes",
  "Deprecations",
];

const ensureIncludes = (path, needles) => {
  const text = read(path);
  const missing = needles.filter((needle) => !text.includes(needle));
  if (missing.length > 0) {
    throw new Error(`${path} is missing: ${missing.join(", ")}`);
  }
};

ensureIncludes("packages/shared/src/schema-version.ts", requiredContractIds);
ensureIncludes("docs/schema-versioning.md", [
  ...requiredContractIds,
  "Breaking changes must include",
  "deprecation-policy.md",
]);
ensureIncludes("CHANGELOG.md", [
  ...requiredContractIds,
  ...requiredChangelogSections,
]);
ensureIncludes("docs/deprecation-policy.md", [
  "Every deprecation must include release-note entries until removal completes.",
]);

process.stdout.write("Schema governance OK: contract ids, changelog sections, and deprecation policy are aligned.\n");
