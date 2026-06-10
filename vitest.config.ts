import { configDefaults, defineConfig } from "vitest/config";

const legacyCddTestGlobs = [
  "packages/mcp-server/src/dude/**/*.test.ts",
  "packages/mcp-server/src/diligence/**/*.test.ts",
  "packages/mcp-server/src/__tests__/e2e/pipeline.test.ts",
  "packages/mcp-server/src/tools/__tests__/brief-tools.test.ts",
  "packages/mcp-server/src/tools/__tests__/query-parity.test.ts",
  "packages/mcp-server/src/tools/__tests__/query-workflows.test.ts",
  "packages/shared/src/__tests__/brief-golden-outputs.test.ts",
  "packages/shared/src/__tests__/query-golden-outputs.test.ts",
] as const;

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    fileParallelism: false,
    include: ["packages/*/src/**/*.test.ts"],
    exclude: [
      ...configDefaults.exclude,
      ...legacyCddTestGlobs,
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["packages/*/src/**/*.ts"],
      exclude: [
        "**/__tests__/**",
        "**/index.ts",
        "**/*.test.ts",
        "**/mock-server/**",
      ],
      thresholds: {
        statements: 80,
        branches: 75,
        functions: 80,
        lines: 80,
      },
    },
    testTimeout: 10000,
    hookTimeout: 10000,
  },
});
