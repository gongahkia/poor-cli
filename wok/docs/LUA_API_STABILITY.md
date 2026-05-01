# Wok Lua API Stability Policy

This document is the contract between Wok and Lua plugin authors. It defines what is stable, what isn't, how new APIs land, how old ones go away, and how versions are tied to wok releases.

If you're a plugin author: write your `init.lua` against the surface guaranteed by this document and pin a minimum wok version in your README. You'll never be silently broken inside a major version.

If you're a wok contributor: every PR that touches `wok-app/src/scripting.rs`, `LUA_SCRIPTING.md`, or `wok.d.lua` must update this document and `lua_hook_payloads.rs` in the same change.

---

## Versioning model

The Lua API uses **independent semantic versioning** decoupled from the wok binary version. The current version is exposed at runtime as `wok.api_version` (string `"MAJOR.MINOR.PATCH"`).

| Bump | When |
|---|---|
| Major (`1.x.x → 2.0.0`) | Any backwards-incompatible change: removed function, renamed namespace, narrowed parameter type, new required field on a hook payload, removed event. |
| Minor (`1.0.x → 1.1.0`) | New function, new namespace, new event, new optional field on a hook payload, new optional parameter on an existing function. |
| Patch (`1.0.0 → 1.0.1`) | Bug fix that doesn't change the contract. Documentation correction. Implementation refactor with identical observable behavior. |

A wok binary version is paired with the highest Lua API version it ships. A plugin can probe at startup:

```lua
local major, minor = wok.api_version:match("^(%d+)%.(%d+)")
if tonumber(major) ~= 1 then
    error("plugin requires Lua API v1.x")
end
```

---

## What's stable (the v1.0 baseline)

The **typed surface** in [`docs/wok.d.lua`](wok.d.lua) is the canonical stability boundary. Every function, namespace, hook event, and class field annotated there is covered by this policy. Anything else is undocumented and unsafe to depend on.

Specifically, v1.0 covers:

- All **functions** in `wok.*` documented in `LUA_SCRIPTING.md` and typed in `wok.d.lua`.
- All **hook events** listed in the hooks table of `LUA_SCRIPTING.md` and aliased as `wok.HookName` in `wok.d.lua`. Each event's payload schema is **pinned by [`tests/lua_hook_payloads.rs`](../wok-app/tests/lua_hook_payloads.rs)** — that test is what enforces this policy.
- All **action ids** documented under "Built-in Action IDs" in `LUA_SCRIPTING.md`. New aliases are minor-bump additions.
- The **sandbox roots** for `wok.fs` (`~/.config/wok/data/`, `~/.local/share/wok/`). New roots are minor; removing one is major.

What is **not** covered:

- Internal Rust types (`scripting.rs::LuaState`, `PluginEffects`, etc.).
- Side effects on the host application beyond the documented behavior of each function (e.g. exact rendering pipeline behavior).
- Performance characteristics. Calls may get faster or slower; we aim for "fast enough" but won't ship a regression suite for plugin throughput.
- Internal hook ordering when multiple plugins register against the same event.

---

## How new APIs land

Every new function, event, or type is annotated with `---@since X.Y.Z` in `wok.d.lua`. Editor tooling shows this on hover; CI lints check that every new public surface gets a `@since`.

```lua
---Cancel a previously scheduled timer.
---@param id integer
---@since 1.0.0
function wok.clear_timer(id) end

---Show the user's profile picture in the title bar.   -- (hypothetical)
---@param url string
---@since 1.4.0
function wok.window.set_avatar(url) end
```

A new event lifts the API minor version and gets:

1. A schema entry in `LUA_SCRIPTING.md` (hooks table).
2. A typed payload class in `wok.d.lua` with `---@since`.
3. An overload added to `wok.on`.
4. A test in `lua_hook_payloads.rs`.
5. A note in [`CHANGELOG.md`](../CHANGELOG.md) under the new minor.

Skipping any of these blocks the merge.

---

## How old APIs go away

Removal is a **two-release process**. Plugins get one full minor cycle of warning before anything breaks.

### Step 1 — Mark deprecated (minor bump that *adds* the deprecation)

```lua
---Old way to copy text.
---@param text string
---@since 1.0.0
---@deprecated since 1.4.0; use `wok.clipboard.copy(text)` instead
function wok.copy_text(text) end
```

The function still works. `lua-language-server` shows a strikethrough + warning on every call site. The Wok runtime logs a one-shot warning on first invocation.

### Step 2 — Remove (major bump)

The deprecated function is deleted from `scripting.rs`, removed from `wok.d.lua`, and the action id (if any) is removed from `parse_lua_action`. `LUA_SCRIPTING.md` adds a "Removed in 2.0" section pointing at the replacement.

A function may not be removed in the same major version it was deprecated in. If it was deprecated in `1.4.0`, the earliest removal is `2.0.0`.

### Hook events follow the same pattern

```lua
---@deprecated since 1.5.0; use "block_started" instead
---| "command_submitted"
```

with a runtime warning when a Lua callback registers for the deprecated name.

---

## Compatibility shims

Renames inside a major version are done with shims, not by breaking the old name:

```lua
-- v1.5: rename pane_api → pane.io for clarity
---@deprecated since 1.5.0; use `wok.pane.io.send_input` instead
wok.pane_api.send_input = wok.pane.io.send_input
```

The shim stays until the next major. Same for renamed actions: keep the old id in `parse_lua_action` until the major bump, with a deprecation warning emitted once per session.

---

## Hook payload evolution

Adding an **optional** field to an existing payload is a minor bump. Tests in `lua_hook_payloads.rs` get a `nil_or_*` entry for the new field; old plugins that ignore it keep working.

Removing a field, renaming a field, or changing a field's type is a **major** bump. Each requires:

1. The replacement field added in the previous minor (deprecation window).
2. The old field marked `---@deprecated` in `wok.d.lua` for one minor.
3. Removal in the next major.

`tab_opened` / `pane_opened` were under-documented prior to v1.0 (commit `f266c6b`). Their post-fix schema is the v1.0 baseline; the under-spec'd version is grandfathered as a documentation bug, not a deprecation event.

---

## Testing requirements

Every shipped Lua API surface has tests. The existing layers:

- `wok-app/tests/lua_hook_payloads.rs` — payload schemas for every documented hook event.
- `wok-app/src/scripting.rs::tests` — unit tests for individual API behaviors (theme set, system_notify, snapshots, sandbox, …).
- `wok-app/src/keybindings_toml.rs::tests` — TOML keybinding parser.

Every PR that adds an API surface adds tests in the appropriate file. The CI gate runs `cargo test --workspace` and refuses to merge on red.

---

## Plugin author checklist

Before publishing your `init.lua` or a wok plugin:

1. **Pin the API version**: `assert(wok.api_version >= "1.0.0", "wok 1.0+ required")`.
2. **Use only typed surfaces**: drop `wok.d.lua` into your editor; if a `wok.X.Y` call shows red, you're depending on something undocumented.
3. **Don't poke runtime internals**: anything reached via `_G` or `debug.*` is unsupported.
4. **Read deprecation logs**: when the runtime warns about a deprecated call, you have one minor cycle to migrate.
5. **Sandbox writes**: never assume `wok.fs` paths can escape — the sandbox is a security boundary, not a convenience layer.

---

## Wok contributor checklist

Adding or changing the Lua API:

- [ ] Implementation in `scripting.rs` with `pub` types & queues as needed.
- [ ] Drainage / handling in `main.rs` (or wherever the side-effect lands).
- [ ] Prose docs in `LUA_SCRIPTING.md`.
- [ ] Type annotation in `wok.d.lua` with `---@since X.Y.Z`.
- [ ] Hook payload test in `lua_hook_payloads.rs` (if a new event).
- [ ] Unit tests in `scripting.rs::tests` (if a new function).
- [ ] `CHANGELOG.md` entry under the next unreleased minor.
- [ ] Bump `wok.api_version` constant.

Removing or renaming:

- [ ] Mark `---@deprecated since X.Y.Z; use Z.Y.Z instead` in `wok.d.lua`.
- [ ] Add a one-shot runtime warning on first invocation.
- [ ] Open a tracking issue for the major-version removal.
- [ ] Document in `LUA_SCRIPTING.md` under "Deprecated".

---

## Out of scope (intentionally)

- **External plugin marketplace** — pending P14.1. Once the marketplace ships, plugins will declare their required API version in their manifest and the resolver will refuse to install a plugin whose minimum is above the running wok's version.
- **Tooling to auto-detect deprecated usage** — `lua-language-server` already shows deprecations from `wok.d.lua` annotations; that's the supported path.
- **Cross-major auto-migration** — you migrate. We provide a one-minor warning window and clear replacements.

---

## CI enforcement

`.github/scripts/lua_api_lint.sh` runs on every PR (job: `lua_api_lint`) and refuses to merge if `docs/wok.d.lua` contains a public `---@class wok.X` or `function wok.x.y(...)` declaration without an `---@since X.Y.Z` annotation in its preceding doc block. Run it locally before pushing:

```bash
./.github/scripts/lua_api_lint.sh
```

Negative-control: temporarily delete an `---@since` line and re-run; the script must exit non-zero. The two test cases (a function missing `@since` and a class missing `@since`) were verified before this lint shipped.
