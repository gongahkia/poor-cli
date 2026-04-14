# Phase Go 07 — Multiplayer Backend Robustness

**Priority:** Unblocks richer collaboration — multi-prompter, presence, attribution, voting. All four features require backend changes to the Python server; Neovim (W8) and Go (W9) depend on this wave landing first.
**Agents:** 4 (all parallel, disjoint files)
**Dependencies:** None from the Go waves. Depends only on the existing `poor_cli/multiplayer*.py` surface.
**Philosophy:** Extend the owner-authoritative model. Do not change the invite/signaling/role primitives. Add capabilities on top. Opt-in via a `multiplayer.features` config block so existing deployments keep the current behaviour.

---

## Reference sources

Authoritative files in the existing backend (all paths relative to `/Users/gongahkia/Desktop/coding/projects/poor-cli/`):

| Concern | File | Lines |
|---|---|---|
| Room transport + queue | `poor_cli/multiplayer.py` | 152–2048 |
| Session state, hand-raise | `poor_cli/multiplayer_session.py` | 16–603 |
| State persistence, approvals | `poor_cli/multiplayer_state.py` | 427–504 |
| Invite format | `poor_cli/multiplayer_invites.py` | 26–134 |
| Server handlers | `poor_cli/server/handlers/multiplayer.py` | 1–126 |
| Lua plugin panels | `nvim-poor-cli/lua/poor-cli/collab.lua`, `multiplayer_room.lua`, `collab_ext.lua` | full |

Readers should grep each file briefly before modifying to understand the existing patterns.

---

## Feature-gate config

All four features land behind a single config block at the top level of `.poor-cli/config.json` (or equivalent). Defaults preserve existing behavior:

```json
{
  "multiplayer": {
    "features": {
      "multiPrompter": false,
      "typingPresence": false,
      "messageAttribution": false,
      "diffVoting": false
    },
    "multiPrompter": {
      "mode": "parallel_queue",
      "maxConcurrent": 1,
      "maxPerUserInFlight": 1
    },
    "typingPresence": {
      "debounceMs": 250,
      "broadcastIntervalMs": 500
    },
    "diffVoting": {
      "threshold": "majority",
      "requiredVoters": 0
    }
  }
}
```

Each agent below owns exactly one feature flag. The config reader in `poor_cli/config.py` (or wherever the existing loader lives) gets one new nested `MultiplayerFeatures` dataclass. All feature checks fall through to `False` when the key is missing.

---

## File-scope table

| Agent | Creates | Modifies |
|-------|---------|----------|
| 7A | `poor_cli/multiplayer_queue.py`, `tests/test_multiplayer_queue.py` | `poor_cli/multiplayer.py` (queue dispatch), `poor_cli/multiplayer_session.py` (role rebalance), `poor_cli/server/handlers/multiplayer.py` (new methods) |
| 7B | `poor_cli/multiplayer_presence.py`, `tests/test_multiplayer_presence.py` | `poor_cli/multiplayer.py` (connection state), `poor_cli/server/handlers/multiplayer.py` (new methods) |
| 7C | `poor_cli/multiplayer_attribution.py`, `tests/test_multiplayer_attribution.py` | `poor_cli/multiplayer.py` (QueuedRequest + broadcast), `poor_cli/server/handlers/chat_streaming.py` (author tag in notifications) |
| 7D | `poor_cli/multiplayer_voting.py`, `tests/test_multiplayer_voting.py` | `poor_cli/multiplayer_session.py` (AgendaItem.votes), `poor_cli/server/handlers/multiplayer.py` (new methods), `poor_cli/server/handlers/diff_review.py` (gate apply on vote threshold) |

### Intra-phase collisions

- **`poor_cli/multiplayer.py`** — 7A adds parallel queue machinery; 7B adds typing state on `ConnectionState`; 7C threads author-id through `QueuedRequest` and broadcast.
- **`poor_cli/multiplayer_session.py`** — 7A extends `rebalance_room_roles` to permit multiple active prompters; 7D adds vote tracking to `AgendaItem`.
- **`poor_cli/server/handlers/multiplayer.py`** — each of 7A/7B/7D adds new `@register(...)` blocks.

### Proposed sub-waves

- **Sub-wave α (fully parallel):** 7B (presence) + 7C (attribution) + 7D (voting). Each touches a distinct subsystem and its own distinct section of the handler file. A brief reconciliation pass on `multiplayer.py` imports + `handlers/multiplayer.py` registration block is required at merge.
- **Sub-wave β (after α):** 7A (multi-prompter). It touches the queue + role system most invasively; landing it last lets the other three features ride into the world with single-prompter semantics first, then flip on when 7A lands.

If schedule demands all four in parallel, 7A can split `multiplayer.py` by line range: the queue-related code stays in a new `multiplayer_queue.py` that imports existing queue primitives, and the in-place edit in `multiplayer.py` is limited to the `_QUEUE_METHODS` set and one line in `_room_worker`.

---

## Agent 7A: Multi-prompter parallel queue

### Goal

Allow multiple approved prompters to submit turns concurrently without rotating the driver. The owner-side serializes LLM calls but round-robins across users so no one is starved. Each user sees their own turn plus everyone else's in the shared transcript.

### Non-goals

- Running parallel LLM calls (still owner-authoritative, still serial dispatch). The parallelism is at the *submission* layer; dispatch remains serial to keep the shared session coherent.
- Giving viewers prompter capability without approval.

### Design

1. **New file `poor_cli/multiplayer_queue.py`** defines a `MultiPrompterQueue` class:
   ```python
   class MultiPrompterQueue:
       def __init__(self, room, *, max_concurrent: int, max_per_user: int): ...
       async def submit(self, connection_id: str, message: JsonRpcMessage) -> str: ...  # returns queue_id
       async def next(self) -> QueuedRequest | None: ...
       async def cancel(self, queue_id: str) -> bool: ...
       def snapshot(self) -> list[dict]: ...  # for listQueue RPC
   ```
   - Round-robin per-user FIFO: maintain `OrderedDict[connection_id, deque[QueuedRequest]]`. On `next`, advance the cursor to the next user with a non-empty queue.
   - `max_per_user` enforced on `submit`: reject with code `-32080` if the user already has `max_per_user` in flight or queued.
2. **Modify `poor_cli/multiplayer.py`**:
   - `_QUEUE_METHODS` stays. In the chat-method branch at line ~1207, when `multiPrompter` feature flag is on, route into `room.multi_queue.submit(...)` instead of the single queue.
   - The `_room_worker` loop pulls from `multi_queue.next()` when present.
   - Broadcast the queue snapshot to all members on every enqueue/dequeue via notification `poor-cli/queueUpdated {roomId, snapshot}`.
3. **Modify `poor_cli/multiplayer_session.py`**:
   - Extend `rebalance_room_roles` to allow any approved member to be prompter when `multiPrompter` is on. Driver concept becomes an optional "focused prompter" (visual hint only) — the actual dispatch is round-robin.
   - Hand-raise queue becomes a passive affordance (no role change required to submit). It remains for explicit focus requests.
4. **New handlers in `poor_cli/server/handlers/multiplayer.py`**:
   - `poor-cli/listRoomQueue` → returns queue snapshot for UI.
   - `poor-cli/cancelQueueItem { queueId }` → owner-only (or author-only) cancel.
5. **Error handling**: if a queued user disconnects mid-queue, drop all their pending items and broadcast `queueUpdated`.

### Tests (`tests/test_multiplayer_queue.py`)

1. Two users submit; queue round-robins correctly (A, B, A, B).
2. `max_per_user=1` rejects a second submission from the same user with `-32080`.
3. User disconnect drops their queued items; queue snapshot reflects the drop.
4. Owner cancel succeeds; author cancel succeeds; non-author cancel is rejected.
5. Feature flag off → falls back to existing single-queue behavior (golden regression test).

### Acceptance criteria

- [ ] Feature flag off → byte-identical behavior to pre-change.
- [ ] Feature flag on → two users can submit turns and both reach the transcript.
- [ ] `poor-cli/queueUpdated` notification fires on every queue mutation.
- [ ] `make lint && make test` passes.
- [ ] No regression in existing `tests/test_multiplayer*.py`.

---

## Agent 7B: Typing presence

### Goal

Broadcast debounced "user X is typing" hints to all room members so everyone knows when a turn is incoming.

### Design

1. **New file `poor_cli/multiplayer_presence.py`** defines `PresenceTracker`:
   ```python
   class PresenceTracker:
       def __init__(self, *, debounce_ms: int, broadcast_interval_ms: int): ...
       def mark_typing(self, connection_id: str) -> bool: ...  # returns True if broadcast needed
       def mark_idle(self, connection_id: str) -> bool: ...
       def snapshot(self) -> dict[str, bool]: ...
   ```
   - State per connection: `{"last_keystroke_at": float, "typing": bool}`.
   - Periodic sweep coroutine: any connection with `now - last_keystroke_at > debounce_ms` flips to idle and broadcasts.
2. **Modify `poor_cli/multiplayer.py`**:
   - Add `room.presence = PresenceTracker(...)` when `typingPresence` feature flag is on.
   - Start a per-room sweep task in the room worker.
   - On inbound `poor-cli/setTyping { typing: bool }` notification, update tracker; if state flipped, broadcast `poor-cli/memberTyping { connectionId, displayName, typing }` to all other members.
3. **New handlers in `poor_cli/server/handlers/multiplayer.py`**:
   - `poor-cli/setTyping { typing: bool }` — client tells server it is typing; server debounces + broadcasts.
   - `poor-cli/listPresence` — returns full presence snapshot for UIs that join mid-session.

### Tests

1. Typing within debounce: only one broadcast.
2. Idle transition: broadcast fires after `debounce_ms + sweep_interval`.
3. Disconnection: tracker removes the connection; a final idle broadcast fires.
4. Feature flag off → `setTyping` returns method-not-found.

### Acceptance criteria

- [ ] No more than `1000 / debounce_ms` broadcasts per user per second.
- [ ] A new joiner receives full presence snapshot via `listPresence`.
- [ ] Goroutine/task cleanup on room teardown.

---

## Agent 7C: Per-user message attribution

### Goal

Every chat message and every streaming response carries the author's `connectionId` + `displayName`. Clients render the author name inline in the transcript (replaces the generic "you" prefix when multiple users are in the room).

### Design

1. **New file `poor_cli/multiplayer_attribution.py`** defines a thin helper:
   ```python
   def author_tag_for(connection_id: str, session) -> dict:
       """Return { 'authorConnectionId', 'authorDisplayName', 'authorRole' }."""
   ```
2. **Modify `poor_cli/multiplayer.py`**:
   - `QueuedRequest` gains an `author` field (set at enqueue).
   - When broadcasting the `chat` method dispatch to all peers (lines ~1805–1843), include `author_tag_for(author_conn_id, room.session)` in the `started` and `finished` events.
3. **Modify `poor_cli/server/handlers/chat_streaming.py`**:
   - At handler start, resolve the current author via the connection context (new param injected from room dispatch, or pulled from a contextvar set when dispatching).
   - Include `authorConnectionId` + `authorDisplayName` in every notification this handler emits: `poor-cli/streamChunk`, `poor-cli/thinkingChunk`, `poor-cli/toolEvent`, `poor-cli/costUpdate`, `poor-cli/progress`.
4. **Back-compat**: in single-player mode, author fields are populated with the local session's identity (`"local"` connection id, display name from env/config). Clients that don't care ignore the fields.
5. **Transcript persistence**: when writing to session history, store author alongside each message so reconnects restore attribution.

### Tests

1. Two users submit turns; notifications for user A's turn carry user A's authorConnectionId.
2. Single-player mode produces `authorConnectionId: "local"` and does not break existing UIs.
3. Session history replay preserves authors.

### Acceptance criteria

- [ ] All streaming notifications include author fields.
- [ ] Existing clients that ignore the fields continue to work.
- [ ] History stored and restored with author intact.

---

## Agent 7D: Shared diff-review voting

### Goal

When the agent produces edits, multiple reviewers can vote approve/reject on each hunk. A hunk applies only when the vote threshold is met (majority or unanimous, configurable). Single-reviewer mode defaults to "one vote applies."

### Design

1. **New file `poor_cli/multiplayer_voting.py`**:
   ```python
   @dataclass
   class HunkVote:
       connection_id: str
       display_name: str
       decision: Literal["approve", "reject"]
       at: float  # epoch ms

   class VoteLedger:
       def __init__(self, *, threshold: Literal["majority","unanimous","owner_only"], required_voters: int): ...
       def record(self, hunk_id: str, vote: HunkVote) -> VoteStatus: ...
       def status(self, hunk_id: str) -> VoteStatus: ...
       def snapshot(self) -> dict[str, list[HunkVote]]: ...
   ```
   `VoteStatus` enum: `Pending | Approved | Rejected`.
2. **Modify `poor_cli/multiplayer_session.py`**:
   - `AgendaItem.votes: VoteLedger | None` (populated when `diffVoting` on).
3. **New handlers in `poor_cli/server/handlers/multiplayer.py`**:
   - `poor-cli/voteOnHunk { editId, hunkId, decision }` — records vote, broadcasts `poor-cli/hunkVoteUpdated` to all members.
   - `poor-cli/getHunkVotes { editId, hunkId }` — returns snapshot.
4. **Gate application in `poor_cli/server/handlers/diff_review.py`**:
   - `poor-cli/acceptHunk` checks vote status when `diffVoting` is on; returns `-32081 HunkVoteNotApproved` if threshold not met.
   - `poor-cli/acceptAll` iterates hunks; skips those without approval.
5. **Broadcast**: `poor-cli/hunkVoteUpdated { editId, hunkId, votes: [...], status }` goes to all members.
6. **Threshold semantics**:
   - `majority` = strictly more than half of currently-connected approved members vote approve; rejections tip to reject when strictly more than half reject.
   - `unanimous` = every currently-connected approved member must approve.
   - `owner_only` = bypass votes; owner decides (legacy behavior).
   - `requiredVoters` (int, default 0) = if >0, require at least this many voters before any decision is final.

### Tests

1. Majority approve (3 users: 2 approve, 1 reject) → approved.
2. Majority borderline (2 users: 1 approve, 1 reject) → pending.
3. Unanimous with 3 approvers → approved.
4. User disconnects during vote → recompute threshold on-the-fly.
5. `owner_only` mode → non-owner votes are recorded but do not affect status.
6. `acceptHunk` rejected when vote pending.

### Acceptance criteria

- [ ] Feature flag off → existing accept/reject flows unchanged.
- [ ] Vote broadcasts reach all members in real time.
- [ ] Legacy `owner_only` mode matches pre-change behavior exactly.

---

## Cross-cutting: protocol additions for clients

All four features expose these new JSON-RPC identifiers. Clients (Neovim, Go) consume them in W8 and W9:

| Kind | Method | Direction | Owner |
|---|---|---|---|
| request | `poor-cli/listRoomQueue` | C→S | 7A |
| request | `poor-cli/cancelQueueItem` | C→S | 7A |
| notification | `poor-cli/queueUpdated` | S→C | 7A |
| request | `poor-cli/setTyping` | C→S | 7B |
| request | `poor-cli/listPresence` | C→S | 7B |
| notification | `poor-cli/memberTyping` | S→C | 7B |
| (augmented) | `poor-cli/streamChunk` etc. include `authorConnectionId`, `authorDisplayName`, `authorRole` | S→C | 7C |
| request | `poor-cli/voteOnHunk` | C→S | 7D |
| request | `poor-cli/getHunkVotes` | C→S | 7D |
| notification | `poor-cli/hunkVoteUpdated` | S→C | 7D |

Wave 1C (protocol types) must be updated to add the corresponding Go structs and method constants. This is a trivial mechanical update — not a new wave — done by whoever lands 7A–D with a one-line PR to `internal/protocol/methods.go`.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Broadcast storm from typing chatter | Debounce + interval broadcast; 500ms interval cap ensures ≤2 msgs/sec/user |
| Queue starvation when one user floods | `max_per_user` cap + round-robin ensures fairness |
| Vote deadlock when users disconnect mid-review | Threshold recomputed against currently-connected members on every recount |
| Breaking existing single-player clients | All four features gated behind `multiplayer.features.*` flags defaulted off |

---

## Acceptance criteria (wave-level)

- [ ] All four feature flags default to OFF; existing deployments are byte-identical after the upgrade.
- [ ] Turning each flag ON activates only that feature; combinations work correctly.
- [ ] All new protocol methods are registered, documented in `orchestration.md`, and exposed to W8 + W9 clients.
- [ ] Full regression suite (`make test`) passes.
- [ ] No new lint warnings.
