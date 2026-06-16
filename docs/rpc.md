# JSONL RPC

`poor-cli rpc serve --stdio` exposes a local JSON-RPC 2.0 server over JSON Lines.

RPC is a secondary integration surface for editors and headless automation. It can classify/run/inspect/replay records, but it is not intended to replace the shim/CLI capture path for daily use.

## Methods

- `route`: returns the same route explanation and optional shim preflight shape as `poor-cli route explain`; it does not create a run or invoke an agent.
- `run`: plans synchronously, starts execution in the background, and returns `{run_id, status}`.
- `status`: returns current run status and summary.
- `inspect`: returns run, task, and event rows.
- `cancel`: requests cancellation for an active run in this RPC process.
- `replay`: returns replay state and optional verification.

## Events

The server emits `poor/event` notifications on stdout as JSON-RPC notifications. Stderr is reserved for diagnostics.

Editors can call `route` before launching an agent, subscribe to `poor/event` notifications during `run`, then call `inspect` or `replay` to render record evidence.

## Boundary

This batch is stdio-only. HTTP, sockets, gRPC, and remote auth are deferred until the JSONL contract proves useful.
