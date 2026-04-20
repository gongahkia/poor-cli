# Plugin Bridge (Out-of-Process)

Wok supports an optional out-of-process plugin bridge process.

Configure it in `config.toml`:

```toml
external_plugin_command = "node ~/.config/wok/plugins/bridge.js"
```

## Input Protocol (Wok -> Bridge)

Wok writes one JSON line per message to bridge stdin.

Hook delivery:

```json
{"kind":"hook","hook":"block_finished","payload":{"pane_id":1}}
```

Runtime event delivery:

```json
{"kind":"event","event":"wok.config","payload":{"shell":"zsh"}}
{"kind":"event","event":"wok.snapshot","payload":{"pane_count":2}}
```

## Output Protocol (Bridge -> Wok)

Bridge writes one JSON line per effect to stdout.

Notification:

```json
{"kind":"notify","message":"plugin ready"}
```

Command execution request:

```json
{"kind":"exec","command":"cargo test -q"}
```

Built-in action request:

```json
{"kind":"action","action":"block_next_failed"}
```

Invalid lines are ignored and surfaced as plugin notifications.
