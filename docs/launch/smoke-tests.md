# Clean Install Smoke Tests

Run these checks from a clean shell with `uv` installed and no editable checkout on `PYTHONPATH`.

## Linux

```console
$ scripts/smoke_uvx_linux.sh
```

Expected result:

- `haus --help` exits successfully through `uvx --from git+https://github.com/gongahkia/haus`.
- `haus mcp --help` prints the MCP entry point.
- `haus view --help` prints the local viewer entry point.

## macOS

```console
$ scripts/smoke_uvx_macos.sh
```

Expected result is the same as Linux. The script intentionally avoids launching a browser so it is safe for CI, SSH sessions, and release checklist use.

## Manual Viewer Check

```console
$ uvx --from git+https://github.com/gongahkia/haus haus view --port 8765
```

Open `http://localhost:8765/viewer/editor.html`, confirm the chat-first shell loads, then stop the process.
