# ADR: Native provider runner

## Decision

Keep shell runners for Codex/Claude and add a provider-backed runner for configured/local providers. The native runner uses the existing provider replay cache, the existing tool dispatcher, provider-neutral tool-call normalization, and deterministic artifacts.

## Rationale

Shell agents remain the compatibility path. Provider-native execution is needed for local/OpenAI-compatible models because a one-shot prompt cannot safely perform repo I/O, replay tool use, or preserve structured run state.

## Contract

The native loop calls a provider with JSON-schema tool definitions, validates tool args before execution, records provider/tool requests and responses, compacts long transcripts deterministically, and writes worker artifacts under the run artifact directory.
