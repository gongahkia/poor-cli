# PRD 012: Keyring-backed credential storage

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small (1–2d)
- **Blocks:** —
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/api_key_manager.py`
  - CLI setup wizard entry points
  - `pyproject.toml` (add `keyring` optional dep)
- **New files it adds:**
  - `tests/test_keyring_credentials.py`

## 1. Problem

API keys for Gemini / OpenAI / Anthropic / OpenRouter land in env vars or the plaintext preferences file. LEARNING.md §2.3: "Credentials live in env vars + plaintext config. Keychain integration is trivial via `keyring` and would be a trust signal."

## 2. Current state

`api_key_manager.py` reads from environment and, optionally, a plaintext config entry. No OS-keyring path.

## 3. Goal & non-goals

**Goal:** API keys can be stored in the OS keyring (Keychain on macOS, Secret Service on Linux, Credential Manager on Windows) via the `keyring` pypi package. Lookup order: keyring → env var → plaintext config. Setup wizard offers to migrate existing env/plaintext keys into the keyring.

**Non-goals:**
- Do not remove env/plaintext fallback (dev ergonomics).
- Do not ship encryption of the plaintext config.

## 4. Design

### 4.1 `keyring` as optional dep

```toml
# pyproject.toml
[project.optional-dependencies]
keyring = ["keyring>=24.0.0"]
```

Graceful degradation: if `keyring` isn't installed, fall back to env/plaintext with an info-level log.

### 4.2 API

```python
class ApiKeyManager:
    def get(self, provider: str) -> str | None: ...
    def set(self, provider: str, key: str, *, store: Literal["keyring","env","config"] = "keyring") -> None: ...
    def migrate_to_keyring(self) -> list[str]:
        """Moves any env/plaintext keys into keyring. Returns providers migrated."""
```

Service name: `"poor-cli"`; username: provider id (`"anthropic"`, etc).

### 4.3 Setup wizard

`poor-cli install` / `poor-cli setup` — after collecting a key, prompt: "Store in OS keyring? [Y/n]".

## 5. Files to create / modify / delete

**Create**
- `tests/test_keyring_credentials.py` — uses a fake keyring backend.

**Modify**
- `poor_cli/api_key_manager.py` — keyring read/write, lookup order, migration.
- CLI entry (installer / setup wizard) — offer migration.
- `pyproject.toml` — add `keyring` to optional deps + `all`.

## 6. Implementation plan

1. Add `keyring` optional dep.
2. Implement keyring read in `get()` before env/plaintext.
3. Implement `set(store=...)`.
4. Implement `migrate_to_keyring()`.
5. Hook into setup wizard.
6. Tests with `keyring.backends.fail.Keyring` and a fake `CryptFileKeyring`.
7. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_lookup_order_keyring_first`
- `test_migration_moves_env_to_keyring`
- `test_missing_keyring_falls_back_gracefully`
- `test_set_rejects_empty_key`

**Done criterion**
- [ ] Keyring lookup works when `keyring` installed.
- [ ] Migration command works.
- [ ] Docs updated with the new storage option.

## 8. Rollback / risk

Low. Fallbacks preserve existing behavior.

## 9. Out-of-scope & boundary

- 🚫 Do not encrypt plaintext config in this PRD.
- 🚫 Do not integrate Vault / 1Password CLIs.

## 10. Related PRDs & references

- LEARNING.md §2.3.
- `keyring`: https://pypi.org/project/keyring/
