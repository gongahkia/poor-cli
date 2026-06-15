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

## Web/MCP Boundary

Web fetch/search and MCP server hosting are not trusted by default. Future network tools must enforce scheme/domain/private-network policy and replayable caches before use in native runner workflows.
