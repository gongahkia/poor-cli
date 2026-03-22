import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { Buffer } from "node:buffer";
import { execFileSync, spawn } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-smoke-"));
const tarballs = [];

const EXPECTED_TOOL_NAMES = [
  "sg_singstat_search",
  "sg_singstat_table",
  "sg_singstat_timeseries",
  "sg_singstat_compare",
  "sg_singstat_browse",
  "sg_mas_exchange_rates",
  "sg_mas_interest_rates",
  "sg_mas_financial_stats",
  "sg_onemap_geocode",
  "sg_onemap_reverse_geocode",
  "sg_onemap_route",
  "sg_onemap_population",
  "sg_onemap_convert_coords",
  "sg_ura_property_transactions",
  "sg_ura_planning_area",
  "sg_ura_dev_charges",
  "sg_datagov_search",
  "sg_datagov_get",
  "sg_datagov_browse",
  "sg_health_check",
  "sg_key_set",
  "sg_key_list",
  "sg_key_delete",
  "sg_cache_stats",
  "sg_cache_clear",
  "sg_config_get",
  "sg_config_set",
  "sg_query",
];

const EXPECTED_RESOURCE_URIS = ["sg://apis", "sg://tools", "sg://workflows"];

const run = (args, cwd = root) => {
  return execFileSync("npm", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  }).trim();
};

class MessageBuffer {
  #buffer = Buffer.alloc(0);
  #queue = [];
  #waiters = [];
  #closedError = null;

  push(chunk) {
    this.#buffer = Buffer.concat([this.#buffer, chunk]);
    this.#drain();
  }

  close(error) {
    this.#closedError = error;
    while (this.#waiters.length > 0) {
      const waiter = this.#waiters.shift();
      waiter.reject(error);
    }
  }

  async next(timeoutMs = 5000) {
    if (this.#queue.length > 0) {
      return this.#queue.shift();
    }
    if (this.#closedError !== null) {
      throw this.#closedError;
    }

    return await new Promise((resolvePromise, rejectPromise) => {
      const waiter = {
        resolve: (message) => {
          clearTimeout(timer);
          resolvePromise(message);
        },
        reject: (error) => {
          clearTimeout(timer);
          rejectPromise(error);
        },
      };
      const timer = setTimeout(() => {
        this.#waiters = this.#waiters.filter((entry) => entry !== waiter);
        rejectPromise(new Error(`Timed out waiting for MCP response after ${timeoutMs}ms`));
      }, timeoutMs);

      this.#waiters.push(waiter);
    });
  }

  #drain() {
    while (true) {
      const headerEnd = this.#buffer.indexOf("\r\n\r\n");
      if (headerEnd === -1) return;

      const headerText = this.#buffer.subarray(0, headerEnd).toString("utf8");
      const lengthMatch = headerText.match(/Content-Length:\s*(\d+)/i);
      if (lengthMatch === null) {
        this.close(new Error(`Missing Content-Length header in MCP frame: ${headerText}`));
        return;
      }

      const contentLength = Number(lengthMatch[1]);
      const messageStart = headerEnd + 4;
      const messageEnd = messageStart + contentLength;
      if (this.#buffer.length < messageEnd) return;

      const payload = this.#buffer.subarray(messageStart, messageEnd).toString("utf8");
      this.#buffer = this.#buffer.subarray(messageEnd);

      let message;
      try {
        message = JSON.parse(payload);
      } catch (error) {
        this.close(new Error(`Failed to parse MCP payload: ${payload}\n${error instanceof Error ? error.message : String(error)}`));
        return;
      }

      if (this.#waiters.length > 0) {
        const waiter = this.#waiters.shift();
        waiter.resolve(message);
      } else {
        this.#queue.push(message);
      }
    }
  }
}

const writeMessage = (stdin, message) => {
  const payload = JSON.stringify(message);
  stdin.write(`Content-Length: ${Buffer.byteLength(payload, "utf8")}\r\n\r\n${payload}`);
};

const request = async (child, buffer, id, method, params = {}) => {
  writeMessage(child.stdin, {
    jsonrpc: "2.0",
    id,
    method,
    params,
  });

  while (true) {
    const message = await buffer.next();
    if (message.id === id) {
      if (message.error !== undefined) {
        throw new Error(`${method} failed: ${JSON.stringify(message.error)}`);
      }
      return message.result;
    }
  }
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

    const messages = new MessageBuffer();
    let settled = false;

    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      child.kill("SIGTERM");
      callback(value);
    };

    child.stdout.on("data", (chunk) => {
      messages.push(chunk);
    });

    child.stderr.on("data", () => {
      // Ignore structured server logs during smoke verification.
    });

    child.once("error", (error) => {
      messages.close(error);
      finish(rejectPromise, error);
    });

    child.once("exit", (code, signal) => {
      const error =
        signal === "SIGTERM" && settled
          ? null
          : new Error(`sg-apis-mcp exited unexpectedly during smoke verification: code=${code}, signal=${signal}`);
      if (error !== null) {
        messages.close(error);
        finish(rejectPromise, error);
      }
    });

    void (async () => {
      try {
        const initializeResult = await request(child, messages, 1, "initialize", {
          protocolVersion: "2025-03-26",
          capabilities: {},
          clientInfo: {
            name: "sg-apis-smoke",
            version: "0.1.0",
          },
        });

        if (initializeResult.serverInfo?.name !== "sg-apis-mcp") {
          throw new Error(`Unexpected MCP server name: ${JSON.stringify(initializeResult.serverInfo)}`);
        }

        writeMessage(child.stdin, {
          jsonrpc: "2.0",
          method: "notifications/initialized",
        });

        const toolsResult = await request(child, messages, 2, "tools/list");
        const resourcesResult = await request(child, messages, 3, "resources/list");

        const toolNames = new Set((toolsResult.tools ?? []).map((tool) => tool.name));
        for (const toolName of EXPECTED_TOOL_NAMES) {
          if (!toolNames.has(toolName)) {
            throw new Error(`Packaged MCP server is missing tool: ${toolName}`);
          }
        }

        const resourceUris = new Set((resourcesResult.resources ?? []).map((resource) => resource.uri));
        for (const uri of EXPECTED_RESOURCE_URIS) {
          if (!resourceUris.has(uri)) {
            throw new Error(`Packaged MCP server is missing resource: ${uri}`);
          }
        }

        finish(resolvePromise);
      } catch (error) {
        messages.close(error);
        finish(rejectPromise, error);
      }
    })();
  });

  process.stdout.write("packaging smoke test passed\n");
} finally {
  for (const tarball of tarballs) {
    rmSync(tarball, { force: true });
  }
  rmSync(tempDir, { recursive: true, force: true });
}
