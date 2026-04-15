# Troubleshooting

## Server Not Found

Error:

```txt
server: poor-cli-server not found
```

Fix:

```sh
python3 -m pip install --upgrade 'poor-cli[all]'
command -v poor-cli-server
```

If the executable is outside `PATH`:

```sh
export POOR_CLI_SERVER_PATH="/absolute/path/to/poor-cli-server"
```

or in config:

```yaml
server_path: /absolute/path/to/poor-cli-server
```

## API Key Prompt

The backend key lookup order is keyring, env var, then plaintext config fallback.

Recommended:

```sh
python3 -m pip install --upgrade 'poor-cli[keyring]'
```

Then use the API-key prompt and keep persistence enabled.

Env fallback:

```sh
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
export GEMINI_API_KEY="..."
export OPENROUTER_API_KEY="..."
```

Status:

```sh
poor-cli provider list
poor-cli config get model.provider
```

## Streaming Appears Frozen

Set a log path before launching:

```sh
mkdir -p "$HOME/.local/state/gocli-poor"
export POOR_CLI_SERVER_LOG_FILE="$HOME/.local/state/gocli-poor/server.log"
gocli-poor
```

Inspect:

```sh
tail -n 100 "$POOR_CLI_SERVER_LOG_FILE"
```

Also verify the backend starts alone:

```sh
poor-cli-server --stdio
```

Quit with `ctrl+c`.

## Colors Look Wrong

Disable color:

```sh
NO_COLOR=1 gocli-poor
```

Force truecolor:

```sh
COLORTERM=truecolor gocli-poor
```

Use 256-color fallback:

```sh
TERM=xterm-256color gocli-poor
```

Terminal capability order:

1. `NO_COLOR` forces monochrome.
2. `COLORTERM=truecolor` or `24bit` enables truecolor.
3. `TERM=xterm-256color` enables ANSI 256.
4. Other terms use ANSI 16.

## Keybinding Fails

Run with a minimal config:

```sh
mv ~/.config/gocli-poor/config.yaml ~/.config/gocli-poor/config.yaml.bak
gocli-poor
```

Common issues:

- `pgdn` and `pagedown` are accepted and normalized to `pgdown`.
- Use `esc`, not `escape`.
- Use comma-separated alternatives: `ctrl+c,esc`.
- Use space-separated chords: `ctrl+x p`.

Reference: [keybindings.md](./keybindings.md).

## Config Not Loading

Check path precedence:

```sh
printf '%s\n' "${XDG_CONFIG_HOME:-$HOME/.config}/gocli-poor/config.yaml"
printf '%s\n' "$HOME/.config/gocli-poor/config.yaml"
printf '%s\n' "$HOME/.gocli-poor.yaml"
```

Only the first existing file is loaded. Env vars override it.

## Windows Terminal Quirks

Use Windows Terminal, PowerShell 7, or a recent terminal with VT processing.

If archive install is used, download the `.zip` release asset and place `gocli-poor.exe` on `PATH`.

If colors render badly:

```powershell
$env:NO_COLOR = "1"
gocli-poor.exe
```

If `ctrl+enter` is intercepted by the terminal, rebind submit:

```yaml
keybindings:
  submit: enter
```

or:

```powershell
$env:GOCLI_POOR_KEYBINDINGS_SUBMIT = "enter"
gocli-poor.exe
```

## Homebrew Install Fails

Update tap metadata:

```sh
brew update
brew install gongahkia/tap/gocli-poor
```

Direct install fallback:

```sh
curl -fsSL https://raw.githubusercontent.com/gongahkia/gocli-poor/main/install.sh | sh
```

## Source Build Fails

Verify Go:

```sh
go version
go test ./...
go build -o ./bin/gocli-poor ./cmd/gocli-poor
```

If `go test ./...` fails, fix that first; the source build uses the same module graph.
