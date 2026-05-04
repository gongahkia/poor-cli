# Roadmap

This document tracks the next practical workstreams for `poor-cli` after the shift to a Python-first harness with a minimal Textual TUI.

## Near-Term

1. Voice runtime bring-up and validation
   - Install and validate the live voice stack end to end.
   - Tune microphone capture, silence detection, transcription latency, and spoken reply behavior.
   - Add better runtime diagnostics for missing voice dependencies and device issues.

2. TUI and harness polish
   - Tighten the transcript and activity flow for long-running agent sessions.
   - Keep the visible feature set narrow and centered on the agent harness.
   - Continue improving approvals, cancellation, and session continuity without turning the TUI into a dashboard.

3. Token-aware budget surfacing
   - Surface per-turn budget controller decisions and adaptive retuning state in the TUI activity pane.
   - Expose compaction, pruning, and compression triggers as inspectable events.
   - Keep budget telemetry first-class — the harness should stay obviously token-aware to its operator.

## Non-Goals

- Multi-user collaboration. The harness is single-operator. Cross-agent collaboration belongs to agent-to-agent flows (sub-agents, parallel agents), not human-to-human shared sessions.
- Dashboard-style UI surfaces.
