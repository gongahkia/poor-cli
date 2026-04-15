# gocli-poor

[![](https://img.shields.io/badge/internal%20coverage-80%25%2B-brightgreen)](https://github.com/gongahkia/poor-cli/actions/workflows/tests.yml)

> A fast, flicker-free TUI chat client for the poor-cli backend.

Demo asciicast: [https://asciinema.org/a/XXXXXX](https://asciinema.org/a/XXXXXX)

## Install

Install the backend first:

```sh
python3 -m pip install --upgrade 'poor-cli[all]'
poor-cli-server --stdio --help
```

Install `gocli-poor`:

```sh
brew install gongahkia/tap/gocli-poor
```

or:

```sh
curl -fsSL https://raw.githubusercontent.com/gongahkia/gocli-poor/main/install.sh | sh
```

or download a release archive from [GitHub Releases](https://github.com/gongahkia/gocli-poor/releases), then put `gocli-poor` on `PATH`.

From this checkout:

```sh
go build -o ./bin/gocli-poor ./cmd/gocli-poor
./bin/gocli-poor --version
```

## Quickstart

```sh
export ANTHROPIC_API_KEY="..."
export POOR_CLI_SERVER_LOG_FILE="$HOME/.local/state/gocli-poor/server.log"
gocli-poor
```

60-second path:

1. Type a prompt in the input line.
2. Press `ctrl+enter`.
3. Use `/provider` to switch provider or model.
4. Use `/cost` to inspect token and cost state.
5. Press `ctrl+q` to quit.

Full walkthrough: [docs/quickstart.md](./docs/quickstart.md).

## Features

- Bubble Tea TUI for `poor-cli-server`.
- Streaming markdown chat.
- Provider/model picker.
- API-key prompt with keyring-backed backend storage.
- Cost, context-pressure, and savings HUDs.
- Diff review, checkpoint, session, permission, and command flows.
- Configurable keybindings and XDG config loading.
- Terminal color fallback for `NO_COLOR`, `COLORTERM`, and `TERM`.

## Configuration

Config guide: [docs/config.md](./docs/config.md).

Default config path:

```txt
$XDG_CONFIG_HOME/gocli-poor/config.yaml
~/.config/gocli-poor/config.yaml
~/.gocli-poor.yaml
```

## Documentation

- [Quickstart](./docs/quickstart.md)
- [Keybindings](./docs/keybindings.md)
- [Config](./docs/config.md)
- [Troubleshooting](./docs/troubleshooting.md)
- [Slash commands](./docs/COMMANDS.md)
- [Providers](./docs/PROVIDERS.md)
- [MCP](./docs/MCP.md)
- [Sandbox](./docs/SANDBOX.md)
- [Multiplayer](./docs/MULTIPLAYER.md)
- [Benchmarks](./docs/BENCHMARKS.md)

## License

MIT
