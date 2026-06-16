# Security

## Shell Tool Policy

The shell tool uses `shlex` only for lexical tokenization. It does not claim to parse full Bash semantics.

Unsupported shell features are denied by default:

- command substitution: `$()`, backticks
- process substitution: `<(...)`, `>(...)`
- heredocs and here-strings
- shell wrappers such as `bash -c`, `sh -c`, and `zsh -c`
- alias/function wrappers
- network-capable commands and URL-like arguments
- redirects outside the workdir

Low-risk commands such as `rg`, `sed`, `python -m pytest`, `git diff`, and `git status` are allowed when they do not use blocked syntax. Blocked commands record the exact reason and remediation in tool artifacts.

## Secrets

Provider config stores env-var references such as `auth = { env = "OPENAI_API_KEY" }`. Plaintext secrets in config are rejected.

Shim capture stores only redacted presence for known secret env vars such as `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `Authorization`, and `X-Api-Key`. The run store also redacts common API-key, token, password, bearer, authorization, and `sk-...` patterns before event or artifact bytes are written.

## Web Tools

`web_search` is disabled until `tools.web.mode` is configured. `web_fetch` accepts only HTTP(S), blocks URL credentials, localhost, private/link-local/reserved IPs, denied domains, and redirects into blocked targets. Fetches record `web.fetch`, `web.cache`, and `web.citation` artifacts for replay and source auditing.

Use `allow_domains` for high-risk runs. `robots.txt` can be enforced with `respect_robots = true`, but it is not an authorization control.

## MCP Boundary

`poor-cli mcp serve --stdio` exposes only allowlisted built-ins by default. Mutating tools are not exposed unless configured. External MCP clients support per-server `allow_tools`, timeout, and secret redaction.
