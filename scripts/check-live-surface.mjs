import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const optionalFile = (rel) => existsSync(resolve(root, rel)) ? [rel] : [];

const checks = [
  {
    label: "runtime mock hooks",
    pattern: "MOCK_API_BASE_URL|getMockApiBaseUrl|mockApiBaseUrl",
    paths: [
      "README.md",
      ...optionalFile("README2.md"),
      ...optionalFile("CHANGELOG.md"),
      "docs",
      "examples",
      "packages/skill",
      "packages/mcp-server/src",
      "packages/shared/src/config",
      "packages/shared/src/index.ts",
    ],
  },
  {
    label: "public fixture references",
    pattern: "golden-outputs|fixture-backed|mock-backed|outside mock mode",
    paths: [
      "README.md",
      ...optionalFile("README2.md"),
      ...optionalFile("CHANGELOG.md"),
      "docs",
      "examples",
      "packages/skill",
      "packages/mcp-server/src/tools",
    ],
  },
];

for (const check of checks) {
  try {
    execFileSync(
      "rg",
      [
        "-n",
        "-g",
        "!**/__tests__/**",
        "-g",
        "!**/fixtures/**",
        check.pattern,
        ...check.paths,
      ],
      {
        cwd: root,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      },
    );

    throw new Error(`Found forbidden ${check.label} references in the live surface.`);
  } catch (error) {
    if (error instanceof Error && "status" in error && error.status === 1) {
      continue;
    }
    if (error instanceof Error) {
      const stderr = "stderr" in error && typeof error.stderr === "string" ? error.stderr.trim() : "";
      const stdout = "stdout" in error && typeof error.stdout === "string" ? error.stdout.trim() : "";
      const details = [stdout, stderr].filter((value) => value !== "").join("\n");
      throw new Error(details === "" ? error.message : details);
    }
    throw error;
  }
}

process.stdout.write("live surface check passed\n");
