// Lightweight syntactic-validity smoke for examples/integration/outcomes/*.ts.
// Type-checks and import-validates each outcome script without spawning the MCP server
// or making upstream calls. Catches the "I broke an outcome example by changing
// the Pulse/Shield payload" class of regression.
import { execFileSync } from "node:child_process";
import { readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const outcomesDir = resolve(root, "examples/integration/outcomes");

const tsFiles = readdirSync(outcomesDir)
  .filter((entry) => entry.endsWith(".ts"))
  .map((entry) => join(outcomesDir, entry))
  .filter((path) => statSync(path).isFile());

if (tsFiles.length === 0) {
  process.stderr.write(`No TypeScript outcome scripts found under ${outcomesDir}\n`);
  process.exit(1);
}

process.stdout.write(`Type-checking ${tsFiles.length} outcome script(s)...\n`);

// tsc --noEmit on each file using the project's existing compiler options.
// We isolate the run so a bad outcome script does not poison the main tsbuildinfo.
const args = [
  "--noEmit",
  "--target", "es2022",
  "--module", "ESNext",
  "--moduleResolution", "Bundler",
  "--strict",
  "--skipLibCheck",
  "--esModuleInterop",
  "--allowImportingTsExtensions",
  ...tsFiles,
];

try {
  execFileSync("npx", ["tsc", ...args], { cwd: root, stdio: "inherit" });
} catch {
  process.stderr.write("Outcome script type-check failed.\n");
  process.exit(1);
}

process.stdout.write("All outcome scripts pass syntactic / type validity.\n");
