# Phase 11: Security & Policy Hardening

**Priority:** High — closes the open security gaps flagged in LEARNING.md §2.3 and LONGTERM-TODO L3 before they become CVE-worthy, then surfaces policy state to users so trust is legible.
**Estimated agents:** 6 (5 parallel in sub-wave A, 1 serialized follow-up in sub-wave B due to one nvim file collision).
**Dependencies:** None external. Intra-phase: **11F serializes after 11E** (shared file — see collision note below).
**Philosophy:** Defense in depth without regression. Every backend agent (11A–11D) ships with a graceful-degradation path so existing env vars / plaintext configs / tight-loop clients keep working while the hardened path becomes the default. The two UI agents (11E, 11F) make what is already enforced *visible* — no new policy semantics, just an honest window into them.

---

## File-scope map (disjointness audit)

| Agent | Primary files | New files |
|-------|---------------|-----------|
| 11A RPC rate limiting | `poor_cli/server/runtime.py`, `poor_cli/server/transport.py` | `poor_cli/server/rate_limit.py`, `tests/test_server_rate_limit.py` |
| 11B Audit log rotation | `poor_cli/audit_log.py`, `poor_cli/cli/` (audit subcommand), scheduler hook | `tests/test_audit_log_rotation.py` |
| 11C Keyring credentials | `poor_cli/api_key_manager.py`, `pyproject.toml`, `poor_cli/cli/` (setup wizard) | `tests/test_keyring_credentials.py` |
| 11D Browser JS sandbox | `poor_cli/browser_tool.py` | `tests/test_browser_tool_sandbox.py` |
| 11E Trust Center | `nvim-poor-cli/lua/poor-cli/trust.lua`, `nvim-poor-cli/lua/poor-cli/commands.lua` | `nvim-poor-cli/tests/trust_spec.lua` |
| 11F Policy Inspector | `nvim-poor-cli/lua/poor-cli/commands.lua` | `nvim-poor-cli/lua/poor-cli/policy_panel.lua`, `nvim-poor-cli/tests/policy_panel_spec.lua` |

### Collisions flagged

- **11E and 11F both mutate `nvim-poor-cli/lua/poor-cli/commands.lua`** (both register a user command — `:PoorCliTrust` and `:PoorCliPolicy` respectively). **Resolution: serialize into sub-waves.** 11E lands first (sub-wave A), 11F rebases on top (sub-wave B). The mutations are purely additive (new command registrations, no shared function bodies), so the rebase is trivial — but running them truly in parallel risks a merge conflict on the same `M.setup()` block. Splitting into A/B is lower friction than trying to pre-carve a shared stub.
- **11B and 11C both touch `poor_cli/cli/`** but each owns a distinct subcommand module (`audit.py` vs. `setup.py` / installer). Confirm on implementation that entries land in different files; if a single `cli/__init__.py` dispatcher needs editing, treat as additive (new subparser) and land sequentially. Not a true collision — noted for vigilance.
- All other file scopes are fully disjoint.

---

## Sub-wave A (parallel): 11A, 11B, 11C, 11D, 11E

## Agent 11A: RPC Rate Limiting

**Pain point addressed:** Unbounded RPC surface — a rogue Lua client or runaway keymap can pound `chatStreaming` in a tight loop, turning a bug into provider spend.
**Expected impact:** Every inbound JSON-RPC call passes a configurable token-bucket limiter; hot methods capped lower than cold methods; excess requests return a structured error instead of blocking the server.

### What to build

A token-bucket rate limiter with per-method-group policy, wired once into the RPC dispatch path. Exceeding the limit returns a JSON-RPC `-32029` error carrying `retry_after_s`; the server stays up.

### Implementation details

1. **Bucket algorithm** — classic token bucket: `capacity` (burst), `tokens` (float), `last_refill` (monotonic), `refill_rate` (tokens/sec). `take(method)` refills lazily on each call, deducts one token, returns `False` when empty.
2. **Config shape** in `preferences.json`:
   ```json
   "rpc_rate_limits": {
     "default":        {"rate": 50, "burst": 100},
     "chatStreaming":  {"rate": 2,  "burst": 4},
     "completions/*":  {"rate": 10, "burst": 20}
   }
   ```
   Lookup: exact method → glob fallback → `default`.
3. **Dispatch integration** — one call site in `runtime.py`: if `not limiter.take(method)` return `JsonRpcError(-32029, "rate limited", {"method": m, "retry_after_s": t})`. Do **not** refactor runtime broadly (PRD 019 owns that).
4. **Observability** — emit `rpc.rate_limit.exceeded` to the audit log with method + client id.
5. **Disable path** — `rpc_rate_limits: {}` turns the limiter into a pass-through. This is also the rollback lever if the limiter misbehaves in production.
6. **Error-code rationale** — `-32029` sits inside the JSON-RPC server-reserved range (`-32000` to `-32099`), so it will not collide with method-level errors.
7. **Non-goals (hard):** no per-user quotas (single local user), no queueing of dropped requests (clients decide whether to retry), no token-count-aware limits (the economy module already does that for LLM calls). Do **not** refactor `runtime.py` broadly — PRD 019 owns partitioning.

### Files to create/modify

- `poor_cli/server/rate_limit.py` (new — `Bucket`, `RateLimiter`, `RateLimitExceeded`)
- `poor_cli/server/runtime.py` (modify — one-line limiter check at dispatch)
- `poor_cli/server/transport.py` (modify — surface the structured error on the wire)
- `tests/test_server_rate_limit.py` (new)

### Acceptance criteria

- [ ] Token-bucket refills over time (unit test)
- [ ] `take()` returns `False` when bucket exhausted
- [ ] Hot methods (`chatStreaming`) limited lower than `default`
- [ ] Glob patterns match method groups
- [ ] Rate-limit exceedance emits audit event
- [ ] RPC integration test: limited client receives `-32029`, server does not die
- [ ] Empty `rpc_rate_limits` config disables limiter with no overhead
- [ ] Config reload replaces buckets without dropping in-flight tokens unexpectedly

---

## Agent 11B: Audit Log Rotation, Archival, and Export

**Pain point addressed:** `.poor-cli/runs.db` grows unbounded — gigabytes after a year of daily use, no archival, no export.
**Expected impact:** Bounded live DB with a size + age cap, monthly gzipped JSONL archives, and an export CLI for ad-hoc ranges.

### What to build

Add `rotate_if_needed()`, `archive()`, and `export_range()` to `audit_log.py`; wire a 1-hour scheduler tick to call rotation; expose `poor-cli audit export --from … --to … --out …`.

### Implementation details

1. **Policy (configurable, defaults in parens):**
   - `audit.max_rows_live` (100,000)
   - `audit.max_age_days_live` (90)
   - `audit.archive_chunk_size` (10,000)
   - `audit.archive_dir` (`.poor-cli/audit/archive/`)
2. **Rotation algorithm** — scheduler runs `rotate_if_needed()` every hour. If either cap is exceeded, stream oldest rows in chunks to `.poor-cli/audit/archive/YYYY-MM.jsonl.gz` and `DELETE … WHERE id IN (…)` in one transaction per chunk. Cap total rotation runtime so the UI never stalls.
3. **Archive format** — one gzipped JSONL file per month, schema = existing audit row schema. Each line a complete record, so downstream tools need no joins.
4. **Export CLI** — `poor-cli audit export --from 2026-01-01 --to 2026-02-01 --out events.jsonl` streams matching rows (live DB + relevant archive files merged) to stdout or a file. Implement as an RPC method (`audit/exportRange`) + thin CLI wrapper.
5. **Atomicity** — each chunk commit is all-or-nothing; SQLite transaction rollback on archive-write failure. Cap per-tick rotation runtime so a backlog cannot stall the UI.
6. **Schema stability** — audit row schema is **unchanged** by this agent (non-goal). PRD 003 owns `meta.schema_version` on this DB.
7. **Non-goals (hard):** no remote sink / centralization; no schema change; no migration of rows already archived.

### Files to create/modify

- `poor_cli/audit_log.py` (modify — add `rotate()`, `archive()`, `export_range()`)
- `poor_cli/cli/` (modify — new `audit` subcommand; land in a new module to avoid collision with 11C)
- Scheduler hook (modify — register 1-hour `rotate_if_needed` tick in whichever module owns background tasks)
- `tests/test_audit_log_rotation.py` (new)

### Acceptance criteria

- [ ] `rotate()` respects `max_rows_live`
- [ ] `rotate()` respects `max_age_days_live`
- [ ] Archive file roundtrips via `export_range()`
- [ ] Rotation is atomic on mid-transaction failure
- [ ] Scheduler ticks rotation every hour
- [ ] Audit row schema **unchanged**
- [ ] `poor-cli audit export` works end-to-end against a synthetic 200k-row DB
- [ ] Archive files validate as gzip + JSONL (one JSON object per line, full row per line)

---

## Agent 11C: OS-Keyring Credential Storage

**Pain point addressed:** Provider API keys live in env vars or plaintext preferences — keyring integration is trivial and a meaningful trust signal.
**Expected impact:** Keys can live in macOS Keychain / Linux Secret Service / Windows Credential Manager. Lookup order becomes keyring → env → plaintext, with a one-shot migration command.

### What to build

Add optional `keyring` dependency and extend `ApiKeyManager` with keyring-aware `get()` / `set(store=…)` / `migrate_to_keyring()`. Setup wizard prompts `"Store in OS keyring? [Y/n]"` after each key entry.

### Implementation details

1. **Optional dep** in `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   keyring = ["keyring>=24.0.0"]
   ```
   Add to the `all` bundle. Graceful degradation: if import fails, log at info level and keep env/plaintext behavior.
2. **Service/user convention** — service = `"poor-cli"`, username = provider id (`"anthropic"`, `"openai"`, `"gemini"`, `"openrouter"`).
3. **API**:
   ```python
   class ApiKeyManager:
       def get(self, provider: str) -> str | None: ...
       def set(self, provider: str, key: str, *,
               store: Literal["keyring","env","config"] = "keyring") -> None: ...
       def migrate_to_keyring(self) -> list[str]: ...
   ```
4. **Lookup order** in `get()`: keyring → `os.environ[PROVIDER_API_KEY]` → plaintext config. First hit wins.
5. **Migration** — `migrate_to_keyring()` walks env + plaintext, writes each found key to keyring, returns the list of providers migrated. Idempotent.
6. **Setup wizard** — after the user pastes a key, prompt to store in keyring. Default = Y when `keyring` importable, else skip the prompt. Entry points: `poor-cli install` / `poor-cli setup`.
7. **Non-goals (hard):** do **not** remove the env/plaintext fallback (dev ergonomics); do **not** encrypt the plaintext config in this phase; do **not** integrate Vault or 1Password CLIs.

### Files to create/modify

- `poor_cli/api_key_manager.py` (modify — keyring read/write, lookup order, migration)
- `pyproject.toml` (modify — `keyring` optional dep + `all` bundle)
- `poor_cli/cli/` setup wizard / installer (modify — offer migration; land in the wizard module, not the `audit` module owned by 11B)
- `tests/test_keyring_credentials.py` (new — use `keyring.backends.fail.Keyring` and a fake `CryptFileKeyring`)

### Acceptance criteria

- [ ] Lookup order: keyring first, then env, then plaintext
- [ ] Migration moves env → keyring and returns the provider list
- [ ] Missing `keyring` package falls back gracefully with an info log
- [ ] `set()` rejects empty keys
- [ ] Env + plaintext fallback paths preserved (dev ergonomics)
- [ ] Setup wizard shows migrate prompt only when keyring is importable
- [ ] No encryption of plaintext config (explicit non-goal)
- [ ] Docs updated to describe the new storage option and lookup order

---

## Agent 11D: Browser Tool JS Sandbox

**Pain point addressed:** `browser_evaluate()` runs arbitrary JS in page context with no timeout, no size limit, and no denylist. Flagged in LONGTERM-TODO L3: "Do it before someone files a CVE."
**Expected impact:** Dangerous patterns blocked by default, bounded output, enforced timeout, explicit permission path for escape hatches.

### What to build

A wrapper around `page.evaluate(js)` that (1) regex-screens the JS for dangerous APIs, (2) wraps the script in an IIFE racing a timeout, (3) serializes and truncates the result, (4) gates `allow_dangerous=True` behind the existing permission callback.

### Implementation details

1. **Defaults:** `DEFAULT_OUTPUT_LIMIT = 64_000` chars, `DEFAULT_TIMEOUT_MS = 5_000`.
2. **Denylist patterns** (regex):
   ```
   localStorage\s*\.\s*clear
   sessionStorage\s*\.\s*clear
   document\s*\.\s*cookie\s*=
   navigator\s*\.\s*sendBeacon
   window\s*\.\s*location\s*=
   indexedDB\s*\.\s*deleteDatabase
   ```
   Match → raise `BrowserEvalBlocked(pattern)` unless `allow_dangerous=True`.
3. **Timeout wrapper** — wrap the user JS in `Promise.race([userFn(), timeoutPromise(timeout_ms)])`; a timeout returns a clean `BrowserEvalTimeout` rather than a raw Playwright error.
4. **Output bounding** — serialize only JSON-serializable values; truncate strings at `max_output` with a trailing marker (e.g., `…[truncated 3412 chars]`).
5. **Permission escalation** — `allow_dangerous=True` funnels through the same permission callback used elsewhere; no silent bypass.
6. **Do not** implement a full JS sandbox or replace Playwright. Rely on Playwright's page-context isolation for the rest.
7. **Non-goals (hard):** do **not** block all `fetch` (legitimate scraping flows rely on it — denylist targets specific sinks only); do **not** add a network proxy layer; do **not** replace Playwright.
8. **Rollback posture:** false-positive denylist hits are handled by the `allow_dangerous=True` escape hatch gated through the permission callback — no silent bypass is ever acceptable.

### Files to create/modify

- `poor_cli/browser_tool.py` (modify — wrap `browser_evaluate`, add policy, timeout, truncation)
- `tests/test_browser_tool_sandbox.py` (new)

### Acceptance criteria

- [ ] `localStorage.clear` blocked
- [ ] `document.cookie = …` blocked
- [ ] Innocent JS runs through unchanged
- [ ] Output above `max_output` is truncated with marker
- [ ] Timeout produces a clean, typed error (not a raw stack)
- [ ] `allow_dangerous=True` routes through permission callback
- [ ] Full coverage of each denylist pattern as individual unit tests
- [ ] `allow_dangerous=True` without a prior permission grant is rejected (no silent bypass)

---

## Agent 11E: Trust Center Interactive Upgrade

**Pain point addressed:** `:PoorCliTrust` is a read-only text dump; users want to toggle sandbox presets, inspect permissions, rotate the audit log, and confirm privacy posture without leaving the buffer.
**Expected impact:** Single-screen interactive scratch buffer with inline `[Toggle sandbox]`, `[View permission rules]`, `[Rotate audit log]`, `[Export audit]` actions bound to `<CR>` on their line.

### What to build

Rewrite `trust.lua` to render sections (Provider, Sandbox preset, Permission mode, Permission rules count, Rollback retention, Audit log state, Privacy, Memory/AGENTS.md source list) with inline action virtual text and line-scoped buffer-local keymaps.

### Implementation details

1. **Data source** — call existing `poor-cli/trustStatus` RPC. If absent, add it (returns a flat object covering every section).
2. **Rendering** — each section has a header and 1–3 data lines; action buttons are virtual text suffixed to specific lines (`[Toggle]`, `[View]`, `[Rotate]`, `[Export]`).
3. **Action wiring** — `nvim_buf_set_keymap` with a line-number check inside the callback; `<CR>` dispatches based on cursor line. Each action invokes a dedicated RPC (`sandbox/toggle`, `permissions/list`, `audit/rotateNow`, `audit/exportRange`) and refreshes the buffer on completion.
4. **Refresh loop** — after any action, re-query `trustStatus` and redraw; no full buffer recreation (preserve cursor).
5. **Section inventory (must all render):** Provider, Sandbox preset, Permission mode, Permission rules count, Rollback (checkpoints retained), Audit log, Privacy (is data leaving the machine?), Memory (AGENTS.md source list).
6. **Non-goal** — do **not** re-implement the general settings UI; that belongs to a future `:PoorCliSettings`. Do **not** modify the audit schema (shared constraint with 11B).

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/trust.lua` (modify — interactive rewrite)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (modify — wire `:PoorCliTrust` to the new renderer; **coordinate with 11F** — this agent lands first)
- `nvim-poor-cli/tests/trust_spec.lua` (new)

### Acceptance criteria

- [ ] Sandbox toggle action switches preset and refreshes buffer
- [ ] `Rotate audit log` action invokes the RPC and reflects new row count
- [ ] All section headers present; no data missing
- [ ] Buffer preserves cursor position across refresh
- [ ] No changes to audit schema (explicit non-goal)
- [ ] All eight sections listed above render with their data lines populated

---

## Sub-wave B (serialized after 11E): 11F

## Agent 11F: Policy Inspector Panel

**Pain point addressed:** Permission rules and policy hooks are opaque — `/policy` dumps them as plain text with no scope, source, or edit affordance.
**Expected impact:** Right-split panel with per-rule rows showing name, scope, outcome (allow/deny/prompt), and source (user / repo / default). Click-to-edit opens the rule file; keymap reloads rules after edit.

### What to build

A new `policy_panel.lua` that renders rules from `poor-cli/policy/list`, binds `<CR>` on a rule line to invoke `policy/edit` (which opens the source file), and binds a reload key to call `policy/reload`.

### Implementation details

1. **RPCs** — `policy/list` (returns `[{name, scope, outcome, source, file, line}]`), `policy/reload` (re-reads from disk), `policy/edit` (returns `{file, line}` for the editor to jump to).
2. **Layout** — right vertical split, fixed width (~60 cols), columns: Outcome | Scope | Name | Source. Color outcomes (allow=green, deny=red, prompt=yellow).
3. **Keymaps (buffer-local):**
   - `<CR>` on a rule row → `policy/edit` → `vim.cmd("edit " .. file)` + jump to line
   - `r` → `policy/reload` → re-render
   - `q` → close panel
4. **Refresh after edit** — autocmd on `BufWritePost` matching the policy file paths triggers `policy/reload` + re-render.
5. **Non-goal** — do **not** change policy engine semantics; this is strictly a viewer/navigator. Outcome labels must match the engine's existing allow/deny/prompt taxonomy exactly.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/policy_panel.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (modify — register `:PoorCliPolicy`; **additive on top of 11E's edits**)
- `nvim-poor-cli/tests/policy_panel_spec.lua` (new)

### Acceptance criteria

- [ ] Rule list renders with all four columns
- [ ] Outcomes colored per convention
- [ ] Reload picks up on-disk changes (autocmd + manual keymap)
- [ ] Edit path opens correct file at correct line
- [ ] Panel closes cleanly with `q`
- [ ] No mutation of policy engine behavior
- [ ] `test_rules_list_renders` and `test_reload_picks_up_disk_change` both pass
