# PoorMac

Native macOS SwiftUI frontend for the `poor-cli` Python backend.

Run from this repo:

```sh
cd apps/PoorMac
swift run PoorMac
```

Verify:

```sh
swift test
```

The app launches `python -m poor_cli.server --stdio` through JSON-RPC Content-Length framing. It defaults to the repo root two levels above this package and prefers `.venv/bin/python` when present.
Provider API keys can be loaded from or saved to macOS Keychain from Settings when a provider name is set.
Chat uses `poor-cli/chatStreaming`, renders stream chunks and activity events, and presents permission/plan review as native sheets.
Provider onboarding, diff review, and the main backend domains use native table/detail or grouped-form layouts; the RPC console remains available for full method coverage.
`make macos-app` builds `dist/macos/PoorMac.app`; `make macos-zip` also creates a distributable zip.

Native UI defaults used:

- `WindowGroup` and `Settings` scene for standard macOS windows/preferences.
- `NavigationSplitView` for Finder-style sidebar navigation.
- `Table`, `List`, `Form`, `ToolbarItem`, `TextEditor`, `SecureField`, and `.sheet(item:)` for standard macOS data, configuration, input, and review surfaces.
- App state is root-owned and injected through SwiftUI environment.
