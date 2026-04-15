# Quickstart

Goal: install backend, launch the Neovim plugin, send one chat turn, switch model, inspect cost.

## 0:00 — Install backend

```sh
python3 -m pip install --upgrade 'poor-cli[all]'
poor-cli --version
```

Supported Python: 3.11, 3.12, 3.13, 3.14.

## 0:30 — Install Neovim plugin

lazy.nvim:

```lua
{ 'gongahkia/poor-cli', dir = '<path>/nvim-poor-cli',
  config = function() require('poor-cli').setup({}) end }
```

From a source checkout:

```sh
./install_nvim_plugin.sh
```

## 1:00 — Configure an API key

```sh
export ANTHROPIC_API_KEY="..."
```

Other supported env vars: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `HF_API_TOKEN`.

## 2:00 — Launch

```sh
nvim
```

Inside Neovim:

- `:PoorCLIStart` — start the backend (auto if `auto_start = true` in setup).
- `:PoorCLIChat` — open the chat panel; send with `<CR>`.

## 3:00 — First turn

Type in the chat input:

```txt
Summarize this repository in 5 bullets.
```

Press `<CR>` to send. Use `:PoorCLIHome` (if `ux.home_nav = true`) to return to the editor.

## 4:00 — Provider and cost

- `:PoorCLIProviders` — pick provider or model.
- `:PoorCLICost` / `:PoorCLICostDashboard` — inspect session tokens and cost.

## Next

- Slash commands: [COMMANDS.md](./COMMANDS.md)
- Providers: [PROVIDERS.md](./PROVIDERS.md)
- Fix startup issues: [troubleshooting.md](./troubleshooting.md)
- Multiplayer: [MULTIPLAYER.md](./MULTIPLAYER.md)
- Neovim plugin README: [../nvim-poor-cli/README.md](../nvim-poor-cli/README.md)
