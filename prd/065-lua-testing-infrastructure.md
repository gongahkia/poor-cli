# PRD 065: Lua testing infrastructure (plenary.busted + CI)

- **Wave:** cross-cutting (do this alongside first Lua-touching PRD)
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small-to-medium (3d)
- **Blocks:** all Lua-touching PRDs that ship tests (014, 015, 016, 029–049, 050–057)
- **Blocked by:** —
- **Files it mutates:**
  - `.github/workflows/tests.yml`
  - `Makefile`
  - `nvim-poor-cli/README.md` (testing section)
- **New files it adds:**
  - `nvim-poor-cli/tests/init.lua`
  - `nvim-poor-cli/tests/minimal_init.lua`
  - `nvim-poor-cli/tests/helpers/mock_rpc.lua`

## 1. Problem

The plugin ships no Lua tests. Pre-commit only runs `luac5.4 -p` for syntax. Every Lua-touching PRD needs plenary.busted to write spec files. The infrastructure must land before the first Lua-test-shipping PRD.

## 2. Current state

`.pre-commit-config.yaml` has a Lua syntax check only. No test runner. No CI job for Lua.

## 3. Goal & non-goals

**Goal:**
- `plenary.nvim` installed as a dev dep into a test-only Neovim runtime.
- `nvim-poor-cli/tests/minimal_init.lua` bootstraps plenary.
- `make test-lua` runs `PlenaryBustedDirectory nvim-poor-cli/tests/` headless.
- CI job runs it on push/PR.
- Mock RPC helper so specs don't need a live `poor-cli-server`.

**Non-goals:**
- Do not fuzz-test the UI.
- Do not run tests against the real server.

## 4. Design

### 4.1 Minimal init

```lua
-- nvim-poor-cli/tests/minimal_init.lua
local plenary_dir = os.getenv("PLENARY_DIR") or vim.fn.stdpath("data") .. "/lazy/plenary.nvim"
vim.opt.rtp:append(".")
vim.opt.rtp:append(plenary_dir)
vim.cmd("runtime plugin/plenary.vim")
require("plenary.busted")
```

### 4.2 Mock RPC

`tests/helpers/mock_rpc.lua` exposes a shim that records calls and lets tests assert them.

### 4.3 CI job

```yaml
lua-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: install neovim
      uses: rhysd/action-setup-vim@v1
      with: { neovim: true, version: v0.10.0 }
    - name: checkout plenary
      uses: actions/checkout@v4
      with: { repository: nvim-lua/plenary.nvim, path: plenary }
    - name: run tests
      run: PLENARY_DIR=$PWD/plenary make test-lua
```

### 4.4 Makefile

```makefile
test-lua: ## run Lua plenary specs
	nvim --headless --noplugin -u nvim-poor-cli/tests/minimal_init.lua \
	  -c "PlenaryBustedDirectory nvim-poor-cli/tests/ {minimal_init = 'nvim-poor-cli/tests/minimal_init.lua'}"
```

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Land minimal_init + mock_rpc.
2. Add Makefile target.
3. Add CI job.
4. Add a placeholder spec (`tests/smoke_spec.lua`) so CI has something to run.
5. Document in `nvim-poor-cli/README.md`.

## 7. Testing & acceptance criteria

- `make test-lua` runs locally (assuming Neovim + plenary present).
- CI job green.

**Done criterion**
- [ ] Infra exists.
- [ ] CI runs.
- [ ] Docs explain how to write specs.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not port existing ad-hoc test files.
- 🚫 Do not test against a real server.

## 10. Related PRDs & references

- plenary.nvim: https://github.com/nvim-lua/plenary.nvim
- Prerequisite for all Lua-touching PRDs with test deliverables.
