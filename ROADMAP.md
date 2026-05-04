# Roadmap

This document tracks the next practical workstreams for `poor-cli` after the shift to a Python-first harness with a minimal Textual TUI.

## Near-Term

1. Voice runtime bring-up and validation
   - Install and validate the live voice stack end to end.
   - Tune microphone capture, silence detection, transcription latency, and spoken reply behavior.
   - Add better runtime diagnostics for missing voice dependencies and device issues.

2. TUI and harness polish
   - Implemented: long-running activity events are compacted instead of flooding the pane.
   - Implemented: cancellation status is explicit when a request is active or absent.
   - Implemented: `/budget` and `/context-status` expose narrow, harness-centered inspection without adding dashboard surfaces.

3. Token-aware budget surfacing
   - Implemented: per-turn budget decisions, compression ratio, model tier, adaptive trend, cost, and latest retuning state surface in the TUI activity pane.
   - Implemented: compaction, pruning, and compression state is exposed through HUD polling and `/context-status`.
   - Implemented: stream notifications for cost, context pressure, economy reports, and progress are rendered as concise activity entries.

## Non-Goals

- Multi-user collaboration. The harness is single-operator. Cross-agent collaboration belongs to agent-to-agent flows (sub-agents, parallel agents), not human-to-human shared sessions.
- Dashboard-style UI surfaces.
