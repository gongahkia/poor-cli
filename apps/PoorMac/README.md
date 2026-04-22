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

Native UI defaults used:

- `WindowGroup` and `Settings` scene for standard macOS windows/preferences.
- `NavigationSplitView` for Finder-style sidebar navigation.
- `Table`, `List`, `Form`, `ToolbarItem`, `TextEditor`, and `SecureField` for standard macOS data, configuration, and input surfaces.
- App state is root-owned and injected through SwiftUI environment.
