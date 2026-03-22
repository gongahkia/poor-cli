import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync, spawn } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-smoke-"));
const tarballs = [];

const run = (args, cwd = root) => {
  return execFileSync("npm", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  }).trim();
};

try {
  const packWorkspace = (workspace) => {
    const output = run(["pack", "--json", "--workspace", workspace]);
    const [{ filename }] = JSON.parse(output);
    const tarballPath = join(root, filename);
    tarballs.push(tarballPath);
    return tarballPath;
  };

  const sharedTarball = packWorkspace("packages/shared");
  const serverTarball = packWorkspace("packages/mcp-server");

  writeFileSync(
    join(tempDir, "package.json"),
    JSON.stringify(
      {
        name: "sg-apis-smoke",
        private: true,
        type: "module",
      },
      null,
      2,
    ),
  );

  run(["install", "--no-package-lock", sharedTarball], tempDir);
  run(["install", "--no-package-lock", serverTarball], tempDir);

  JSON.parse(readFileSync(join(tempDir, "node_modules", "sg-apis-mcp", "package.json"), "utf8"));
  JSON.parse(readFileSync(join(tempDir, "node_modules", "@sg-apis", "shared", "package.json"), "utf8"));

  await new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(join(tempDir, "node_modules", ".bin", "sg-apis-mcp"), [], {
      cwd: tempDir,
      env: { ...process.env, SG_APIS_LOG_LEVEL: "error" },
      stdio: ["pipe", "pipe", "pipe"],
    });

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      resolvePromise();
    }, 1000);

    child.once("exit", (code, signal) => {
      clearTimeout(timer);
      if (signal === "SIGTERM" || code === 0) {
        resolvePromise();
        return;
      }
      rejectPromise(new Error(`sg-apis-mcp exited unexpectedly: code=${code}, signal=${signal}`));
    });

    child.once("error", (error) => {
      clearTimeout(timer);
      rejectPromise(error);
    });
  });

  process.stdout.write("packaging smoke test passed\n");
} finally {
  for (const tarball of tarballs) {
    rmSync(tarball, { force: true });
  }
  rmSync(tempDir, { recursive: true, force: true });
}
