# Quickstart

Asciicast: [https://asciinema.org/a/XXXXXX](https://asciinema.org/a/XXXXXX)

Goal: install backend, launch `gocli-poor`, send one chat turn, switch model, inspect cost, quit.

## 0:00 - Install

```sh
python3 -m pip install --upgrade 'poor-cli[all]'
poor-cli-server --stdio --help
```

Install the TUI:

```sh
brew install gongahkia/tap/gocli-poor
```

or:

```sh
curl -fsSL https://raw.githubusercontent.com/gongahkia/gocli-poor/main/install.sh | sh
```

From a source checkout:

```sh
go build -o ./bin/gocli-poor ./cmd/gocli-poor
```

## 1:00 - Configure a key

Use one provider key:

```sh
export ANTHROPIC_API_KEY="..."
```

Other backend-supported env vars include `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `OPENROUTER_API_KEY`.

Optional log path:

```sh
mkdir -p "$HOME/.local/state/gocli-poor"
export POOR_CLI_SERVER_LOG_FILE="$HOME/.local/state/gocli-poor/server.log"
```

## 2:00 - Launch

```sh
gocli-poor
```

If the server is not on `PATH`:

```sh
export POOR_CLI_SERVER_PATH="$(command -v poor-cli-server)"
gocli-poor
```

## 3:00 - First turn

Type:

```txt
Summarize this repository in 5 bullets.
```

Press `ctrl+enter`.

While streaming, use:

- `ctrl+j` to focus chat.
- `pgup` / `pgdown` to scroll.
- `ctrl+i` or `esc` to return to input.

## 4:00 - Provider and cost

Open provider picker:

```txt
/provider
```

Use `up` / `down` to choose a provider and `left` / `right` to cycle models. Press `enter`.

Open cost:

```txt
/cost
```

Quit:

```txt
ctrl+q
```

## 5-Minute Video Script

0:00 - Title: "gocli-poor in 5 minutes". Show terminal with `python3 -m pip install --upgrade 'poor-cli[all]'`.

0:30 - Run `poor-cli-server --stdio --help`. Say this confirms the backend executable is visible.

1:00 - Install TUI with Homebrew or `install.sh`. Run `gocli-poor --version`.

1:30 - Export one API key and `POOR_CLI_SERVER_LOG_FILE`. Explain key lookup: backend keyring, env var, then config fallback.

2:00 - Launch `gocli-poor`. Wait for the intro line to clear.

2:30 - Send "Summarize this repository in 5 bullets." with `ctrl+enter`.

3:15 - Scroll the chat with `ctrl+j`, `pgup`, `pgdown`, then return to input with `ctrl+i`.

3:45 - Type `/provider`, pick another model, press `enter`.

4:15 - Type `/cost`, point out session cost and context pressure.

4:45 - Mention docs: config, keybindings, troubleshooting. Quit with `ctrl+q`.

## Next

- Rebind keys: [keybindings.md](./keybindings.md)
- Tune config: [config.md](./config.md)
- Fix startup issues: [troubleshooting.md](./troubleshooting.md)
