# @swee-sg/sdk

Typed REST client for Swee SG gateways.

## Scope

The SDK is intentionally thin:

- it calls the existing REST gateway under `/api/v1`;
- it validates Pulse and Shield convenience inputs;
- it unwraps gateway `data` envelopes for common tool calls;
- it does not reimplement Singapore source-adapter or signal logic client-side.

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

```ts
import { createSweeClient } from "@swee-sg/sdk";

const swee = createSweeClient({
  baseUrl: "https://swee.example",
  token: process.env.SWEE_API_TOKEN,
});

const snapshot = await swee.pulseSnapshot({ focus: "all" });
const explanation = await swee.pulseExplain();
const auditRows = await swee.shieldAudits({ limit: 10 });

console.log(snapshot.signals, explanation.aiUsed, auditRows.records);
```

Generic tool calls are available when the caller already knows the stable MCP tool contract:

```ts
const payload = await swee.callTool("sg_nea_forecast_2hr", {
  area: "Bedok",
});
```

## API Surface

| API | Purpose |
| --- | --- |
| `createSweeClient(options)` | Creates a client instance. |
| `new SweeClient(options)` | Class form for dependency injection and tests. |
| `client.health()` | Reads `/api/v1/health`. |
| `client.listTools()` | Reads `/api/v1/tools`. |
| `client.callTool<T>(toolName, input)` | Calls `POST /api/v1/<toolName>` and unwraps gateway `data`. |
| `client.pulseSnapshot(input)` | Calls `swee_pulse_snapshot`. |
| `client.pulseMobility()` | Calls `swee_pulse_mobility`. |
| `client.pulseWeather(input)` | Calls `swee_pulse_weather`. |
| `client.pulseExplain(input)` | Calls deterministic `swee_pulse_explain`. |
| `client.shieldAudits(input)` | Calls `swee_shield_audit_lookup`. |
| `client.shieldScan()` | Calls `swee_shield_scan_tools`. |
| `SweeApiError` | Error type with `status` and raw `payload` from failed gateway responses. |

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

Current blocker: publish only after the maintainer account and hosted token/auth story are finalized. Until then, use the workspace package locally or consume a GitHub tarball from a tagged release.
