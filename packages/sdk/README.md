# @swee-sg/sdk

Typed REST client for Dude Cloud and self-hosted Dude MCP gateways.

## Scope

The SDK is intentionally thin:

- it calls the existing REST gateway under `/api/v1`;
- it validates high-value inputs with the shared Dude schemas;
- it unwraps gateway `data.record` envelopes for common tool calls;
- it does not reimplement Singapore data logic client-side.

## Install

After the package is public on npm:

```bash
npm install @swee-sg/sdk
```

For local development inside this monorepo, build the workspace first:

```bash
npm run build
```

## Usage

Use the workspace package locally or a GitHub tarball from a tagged release until npm publication is complete. The import path below is the intended public package name after publication.

```ts
import { createDudeClient } from "@swee-sg/sdk";

const dude = createDudeClient({
  baseUrl: "https://dude.example",
  token: process.env.DUDE_API_TOKEN,
});

const report = await dude.cddReport({
  uen: "201900001A",
  includeContextIds: true,
});

console.log(report.dossier.summary);
```

Generic tool calls and low-level compatibility APIs are available when the caller already knows the stable `sg_*` contract:

```ts
const dossier = await dude.businessDossier({
  uen: "201900001A",
});
```

## API Surface

| API | Purpose |
| --- | --- |
| `createDudeClient(options)` | Creates a client instance. |
| `new DudeClient(options)` | Class form for dependency injection and tests. |
| `client.health()` | Reads `/api/v1/health`. |
| `client.listTools()` | Reads `/api/v1/tools`. |
| `client.callTool<T>(toolName, input)` | Calls `POST /api/v1/<toolName>` and unwraps `data.record` if present. |
| `client.cddReport(input)` | Validates input and calls the product CDD orchestrator. |
| `client.businessDossier(input)` | Low-level compatibility method for `sg_business_dossier`. |
| `client.query(input)` | Validates and calls `sg_query`. |
| `DudeApiError` | Error type with `status` and raw `payload` from failed gateway responses. |

## Options

| Option | Meaning |
| --- | --- |
| `baseUrl` | Gateway base URL. Defaults to `http://localhost:3000`. |
| `token` | Optional bearer token for hosted or protected gateways. |
| `headers` | Static or async headers for customer-specific auth and tracing. |
| `fetch` | Custom fetch implementation for tests or nonstandard runtimes. |
| `timeoutMs` | Optional client-side request timeout. |

## Publish Readiness

Dry-run from the repo root:

```bash
npm run sdk:pack:dryrun
```

Current blocker: the package should not be published to npm until the maintainer account has the `@dude` npm scope available and the hosted token/auth story is finalized. Until then, use the workspace package locally or consume a GitHub tarball from a tagged release.
