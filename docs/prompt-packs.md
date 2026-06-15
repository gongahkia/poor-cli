# Prompt Packs

Prompt packs are local, versioned prompt templates selected by route role.

```sh
poor-cli prompt packs --json
poor-cli prompt efficiency --before old.txt --after new.txt
```

Built-ins:

- `planner.default`
- `executor.native`
- `reviewer.anti_sycophancy`
- `verifier.default`
- `graph.navigator`

Custom packs live in `.poor-cli/prompt-packs.toml` under `packs`. Each pack must record `id`, `version`, `license`, `source_url`, `scope`, `roles`, `template`, `arguments`, and `provenance_status`.

Allowed provenance values:

- `local-authored`
- `user-provided`
- `permissive-source-summary`

Copied external prompt text is rejected unless provenance and license are explicit.

## Route Selection

```toml
[routes.reviewer]
profile = "reviewer"
model = "review-model"
prompt_pack = "reviewer.anti_sycophancy"
```
