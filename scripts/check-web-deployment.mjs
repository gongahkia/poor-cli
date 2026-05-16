import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

const read = (path) => readFileSync(resolve(root, path), "utf8");
const assertIncludes = (name, content, pattern) => {
  if (!content.includes(pattern)) {
    throw new Error(`${name} is missing required deployment marker: ${pattern}`);
  }
};

const dockerfile = read("Dockerfile");
assertIncludes("Dockerfile", dockerfile, "COPY apps/web/package.json apps/web/");
assertIncludes("Dockerfile", dockerfile, "COPY apps/web apps/web");
assertIncludes("Dockerfile", dockerfile, "npm run build -w apps/web");
assertIncludes("Dockerfile", dockerfile, "COPY --from=build /app/apps/web/dist apps/web/dist");
assertIncludes("Dockerfile", dockerfile, "COPY --from=build /app/packages/mcp-server/dist packages/mcp-server/dist");

const caddyfile = read("Caddyfile");
assertIncludes("Caddyfile", caddyfile, "@api path /api/v1 /api/v1/*");
assertIncludes("Caddyfile", caddyfile, "reverse_proxy @api dude-gateway:3000");
assertIncludes("Caddyfile", caddyfile, "@mcp path /mcp /healthz /icon.svg");
assertIncludes("Caddyfile", caddyfile, "root * /srv/dude");
assertIncludes("Caddyfile", caddyfile, "try_files {path} /index.html");
assertIncludes("Caddyfile", caddyfile, "file_server");

const compose = read("compose.yaml");
assertIncludes("compose.yaml", compose, "dude-gateway:");
assertIncludes("compose.yaml", compose, "dude-assets:");
assertIncludes("compose.yaml", compose, "DUDE_WEB_ORIGIN_ALLOWLIST");
assertIncludes("compose.yaml", compose, "packages/mcp-server/dist/rest-gateway.js");
assertIncludes("compose.yaml", compose, "dude-mcp:");
assertIncludes("compose.yaml", compose, "dude_web_assets:");

const deploymentDocs = read("docs/deployment.md");
assertIncludes("docs/deployment.md", deploymentDocs, "/api/v1");
assertIncludes("docs/deployment.md", deploymentDocs, "DUDE_WEB_ORIGIN_ALLOWLIST");
assertIncludes("docs/deployment.md", deploymentDocs, "MCP");

process.stdout.write("web deployment check passed\n");
