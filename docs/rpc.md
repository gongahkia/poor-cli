# JSONL RPC

`poor-cli rpc serve --stdio` exposes a local JSON-RPC 2.0 server over JSON Lines.

## Methods

- `run`: plans synchronously, starts execution in the background, and returns `{run_id, status}`.
- `status`: returns current run status and summary.
- `inspect`: returns run, task, and event rows.
- `cancel`: requests cancellation for an active run in this RPC process.
- `replay`: returns replay state and optional verification.

## Events

The server emits `poor/event` notifications on stdout as JSON-RPC notifications. Stderr is reserved for diagnostics.

## Boundary

This batch is stdio-only. HTTP, sockets, gRPC, and remote auth are deferred until the JSONL contract proves useful.
