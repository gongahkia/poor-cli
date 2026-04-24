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

3. Multiplayer architecture and backend foundations
   - Build the shared-session primitives before exposing a network attach flow.
   - Keep multiplayer centered on a host-admin model, a foreground prompt queue, task threads, merge requests, and approval templates.

## Multiplayer Exploration

The target multiplayer model is one hosted shared session with a host and peers.
The host is the admin because they started the session and own the local harness process.
Peers are otherwise full participants: they can prompt, edit their queued prompts, start task threads, spawn or assign agents, and participate in approvals when an approval template allows them.

The main session has three work lanes:

- Foreground queue: the shared conversation thread. It is first-come, first-served by default, with one active foreground prompt at a time. The host can move queued prompts up or down, remove queued items, and clear stuck work.
- Task threads: side lanes inside the same shared session. A task thread is a lightweight work item with comments, agent runs, approvals, artifacts, and a lifecycle.
- Agent runs: autonomous workers attached to either the foreground session or a task thread. Agents remain visible in the shared session but run in their own execution contexts, usually isolated worktrees.

Task threads can merge back into the main session. The merge is Git-like but broader: file changes are reviewed alongside a context summary, decisions, approvals, test results, and links to raw thread logs. The main transcript should receive the reviewed summary and references, not the entire side-thread transcript.

## Multiplayer Design Questions

1. Queue execution
   - How should queued prompts be edited, cancelled, promoted, demoted, and started?
   - What should happen when the active foreground prompt fails or is cancelled?

2. Thread merging
   - What exactly becomes part of the main transcript when a task thread merges?
   - How should file diffs, summaries, decisions, and follow-up tasks be represented together?

3. Approval templates
   - Which events need templates: plan review, PRD review, risky writes, destructive commands, merge requests?
   - Should templates require a count, named people, the host, or a combination?

4. Agent orchestration
   - Are agents attached to the foreground session, task threads, or both?
   - How are file ownership, worktree isolation, and merge conflicts surfaced?

5. Transport and runtime shape
   - Is the first attachable runtime a local socket, LAN server, or WebSocket server?
   - How are participant identity and session join secrets handled?

6. Audit and replay
   - How are prompts, queue edits, thread events, approvals, agent actions, and merges recorded?
   - Can a hosted session be resumed and replayed from the event log?

## Suggested Multiplayer V1

The first version should stay narrow:

1. One shared repo session hosted by one local harness process.
2. One host participant plus full peer participants.
3. A first-come foreground queue that the host can reorder.
4. Task threads for parallel side work inside the same shared session.
5. Merge requests from task threads back to the main session.
6. Approval templates for plans, PRDs, risky actions, and merges.
7. Shared UI surfaces for presence, queue, task threads, approvals, agents, and transcript.

This keeps multiplayer aligned with the current product direction: an agent harness first, not a feature-heavy collaboration suite.

## Exit Criteria For The Design Phase

Before multiplayer implementation begins, the project should have:

- a written session model
- a permissions model
- a foreground queue model
- a task-thread and merge model
- an approval-template model
- a transport decision
- a minimal CLI UX proposal
- a clear V1 scope with explicit non-goals
