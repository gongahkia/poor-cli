# Roadmap

This document tracks the next practical workstreams for `poor-cli` after the shift to a Python-first harness with a minimal `curses` TUI.

## Near-Term

1. Voice runtime bring-up and validation
   - Install and validate the live voice stack end to end.
   - Tune microphone capture, silence detection, transcription latency, and spoken reply behavior.
   - Add better runtime diagnostics for missing voice dependencies and device issues.

2. TUI and harness polish
   - Tighten the transcript and activity flow for long-running agent sessions.
   - Keep the visible feature set narrow and centered on the agent harness.
   - Continue improving approvals, cancellation, and session continuity without turning the TUI into a dashboard.

3. Multiplayer architecture exploration
   - Brainstorm what a multiplayer CLI coding agent should be from scratch before implementing any transport or UI.
   - Treat this as a product and systems-design track first, not a coding track.

## Multiplayer Exploration

The next major design question is how `poor-cli` could support a multiplayer mode where more than one human and more than one agent can collaborate inside the same coding session.

The first step is to define the model clearly:

- Is multiplayer one shared workspace with multiple humans?
- Is it one human supervising multiple agents in parallel?
- Is it several humans and several agents sharing the same task graph?
- Is the session local-only, LAN-based, or networked across machines?

The design work should answer these questions before implementation starts.

## Multiplayer Design Questions

1. Session model
   - What is the unit of collaboration: repo, branch, task, conversation, or workspace?
   - Does multiplayer create one shared session log or several linked sessions?

2. Roles and permissions
   - What can a participant do: observe, chat, approve, assign work, run tools, merge results?
   - How are tool permissions scoped per participant and per agent?

3. Agent orchestration
   - How are parallel agents assigned ownership over files, tasks, or subsystems?
   - How are collisions, duplicate work, and conflicting edits prevented?

4. State synchronization
   - What state must be shared live: transcript, plans, approvals, diffs, task ownership, diagnostics, presence?
   - Does the system need optimistic updates, locks, or a CRDT-style event log?

5. UX inside a CLI
   - How does a terminal surface show presence, assignments, and live activity without becoming noisy?
   - What is the minimum viable multiplayer UX for a harness-first CLI?

6. Transport and runtime shape
   - Is stdio still enough, or does multiplayer require a long-lived local server with sockets or WebSockets?
   - How should remote participants attach to a running session?

7. Audit and replay
   - How are actions, approvals, tool calls, and handoffs recorded?
   - Can a multiplayer session be replayed or resumed deterministically?

## Suggested Multiplayer V1

If multiplayer is pursued, the first version should stay narrow:

1. One shared repo session.
2. One host process runs the harness.
3. Multiple human participants can attach as observers or approvers.
4. The host can spin up multiple agents and assign them scoped tasks.
5. The shared UI exposes presence, active tasks, approvals, and transcript only.

This keeps multiplayer aligned with the current product direction: an agent harness first, not a feature-heavy collaboration suite.

## Exit Criteria For The Design Phase

Before multiplayer implementation begins, the project should have:

- a written session model
- a permissions model
- a task ownership model for parallel agents
- a transport decision
- a minimal CLI UX proposal
- a clear V1 scope with explicit non-goals
