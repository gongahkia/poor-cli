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

If the executable is outside `PATH`, point the Neovim plugin at it:

```lua
require('poor-cli').setup({
    server_cmd = '/absolute/path/to/poor-cli-server --stdio',
})
```

## API Key Prompt

The backend key lookup order is keyring, env var, then plaintext config fallback.

Recommended:

```sh
python3 -m pip install --upgrade 'poor-cli[keyring]'
```

Env fallback:

```sh
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
export GEMINI_API_KEY="..."
export OPENROUTER_API_KEY="..."
```

Check status:

```sh
poor-cli provider list
poor-cli config get model.provider
```

Inside Neovim, `:checkhealth poor-cli` reports which keys are present.

## Streaming Appears Frozen

Inspect server logs:

```sh
tail -n 100 "$(nvim --headless +'lua print(require("poor-cli.config").get_server_log_file())' +qa 2>&1 | tail -n1)"
```

Or set a custom log path in setup:

```lua
require('poor-cli').setup({
    server_log_file = vim.fn.expand('~/.local/state/poor-cli/server.log'),
})
```

Verify the backend starts standalone:

```sh
poor-cli-server --stdio
```

## Plugin loaded but `:PoorCLI…` commands missing

Make sure `require('poor-cli').setup({})` actually ran. On `VimEnter`, the plugin prints a warning if `setup()` was never called.

## Config Not Loading

The Neovim plugin reads options from the `setup({...})` call — it does not consult a YAML file. If values don't take effect:

1. Confirm `setup()` is called *after* your other plugin bootstrap.
2. `:lua = require('poor-cli.config').sanitized_for_debug()` — dump the live merged config.

## Completion Disabled in a Buffer

Run `:PoorCLICompletionReason` (requires `ux.completion_reason = true`) to see why. Typical causes:

- Filetype is in `completion_filetype_blocklist`.
- Buftype is in `completion_buftype_blocklist` (e.g. `nofile`, `terminal`).
- `completion_manual_only = true` and no manual trigger.

Toggle for the current filetype: `:PoorCLICompletionToggle`.

## Multiplayer Room Won't Connect

- Both sides must run the same backend version.
- Use `:PoorCLICollabQuick` to generate/accept invites; paste whole invite string.
- `:PoorCLIStatus` reports the room + role.

## `:checkhealth poor-cli`

Always start here:

```vim
:checkhealth poor-cli
```

Reports Neovim version, server executable, log dir, Python version, API keys, plugin integrations (nvim-cmp, blink.cmp, treesitter), and domain modules.

With `ux.health_actions = true`, the report appends actionable `:PoorCLIOnboarding` / `:PoorCLIStart` hints.

## Reference

- [quickstart.md](./quickstart.md)
- [COMMANDS.md](./COMMANDS.md)
- [PROVIDERS.md](./PROVIDERS.md)
- Neovim plugin README: [../nvim-poor-cli/README.md](../nvim-poor-cli/README.md)
