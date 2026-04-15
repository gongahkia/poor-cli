# Phase Go 08 — Neovim Multiplayer UI

**Priority:** Surfaces the new backend features to real users. Neovim ships first because it is the existing, dogfooded frontend; landing here lets us stabilize UX before porting to Go.
**Agents:** 3 (all parallel, disjoint files)
**Dependencies:** Wave 7 (backend features must exist). Can run in parallel with Wave 9 (Go) once W7 lands.
**Philosophy:** Minimal UI delta on the Lua side. Reuse the existing `collab.lua` + `multiplayer_room.lua` scaffolding wherever possible. Add one dedicated users panel, extend the chat renderer with attribution + typing, and add inline vote actions to the diff review pane.

---

## Reference sources (Lua plugin)

| Concern | File |
|---|---|
| Existing collab panel | `nvim-poor-cli/lua/poor-cli/collab.lua` |
| Room snapshot | `nvim-poor-cli/lua/poor-cli/multiplayer_room.lua` |
| Admin commands | `nvim-poor-cli/lua/poor-cli/collab_ext.lua` |
| Chat panel (attribution hook here) | `nvim-poor-cli/lua/poor-cli/chat.lua` |
| Diff review panel | `nvim-poor-cli/lua/poor-cli/diff_review.lua` |
| RPC client | `nvim-poor-cli/lua/poor-cli/rpc.lua` |
| Panel scaffolding pattern | `nvim-poor-cli/lua/poor-cli/panel_base.lua` (if exists — else follow the pattern used by `timeline.lua`) |

---

## File-scope table

| Agent | Creates | Modifies |
|---|---|---|
| 8A | `nvim-poor-cli/lua/poor-cli/users_panel.lua`, `nvim-poor-cli/tests/users_panel_spec.lua` | `nvim-poor-cli/lua/poor-cli/init.lua` (register panel), `nvim-poor-cli/lua/poor-cli/rpc.lua` (subscribe to `memberTyping`, `queueUpdated`) |
| 8B | `nvim-poor-cli/lua/poor-cli/chat_attribution.lua`, `nvim-poor-cli/tests/chat_attribution_spec.lua` | `nvim-poor-cli/lua/poor-cli/chat.lua` (inject author prefix + typing footer) |
| 8C | `nvim-poor-cli/lua/poor-cli/diff_voting.lua`, `nvim-poor-cli/tests/diff_voting_spec.lua` | `nvim-poor-cli/lua/poor-cli/diff_review.lua` (vote keymaps + vote row render) |

### Intra-phase collisions

- **`nvim-poor-cli/lua/poor-cli/init.lua`** — 8A registers the users panel and its commands. 8B/8C do not touch it.
- **`nvim-poor-cli/lua/poor-cli/rpc.lua`** — 8A adds notification subscriptions; 8B subscribes to `poor-cli/streamChunk` with attribution fields (field additions, no new subscription); 8C subscribes to `poor-cli/hunkVoteUpdated`. All three touch the `notification_handlers` table. Split by key name — each agent adds its own key; no conflict in practice.

### Proposed sub-waves

Fully parallel. Final merge requires a trivial reconciliation of `rpc.lua` and `init.lua` handler tables.

---

## Agent 8A: Users side panel

### Goal

A dedicated panel listing every room member with role, approval state, presence, and quick actions. Opened via `:PoorCLIUsers` or focus keybind (default `<leader>pu`). Pins to a fixed-width vertical split on the right.

### Panel layout (text only, Neovim convention)

```
users (4)
───────────────────────────────────
 alice        owner     driver
              ● typing…
 bob          prompter  approved
              #3 in queue
 carol        prompter  approved
              voted on 2/3 hunks
 dave         viewer    pending
              [a]approve [d]deny
```

Role icons:
- `owner` — no icon (default)
- `prompter` — muted `>` prefix
- `viewer` — muted `·` prefix
- `driver` — suffix `← driver` if single-prompter mode; suffix `→ focused` if multi-prompter and this member is the focused prompter

Presence:
- `● typing…` in accent color when `memberTyping` is true
- `◌ idle` in muted when idle (suppressed by default; only shown when debug flag on)

Quick actions per row (keymap while row is focused):
- `a` → approve pending member (`poor-cli/approveHostMember`)
- `d` → deny pending member (`poor-cli/denyHostMember`)
- `r` → change role (opens input: `viewer|prompter`; calls `poor-cli/setHostMemberRole`)
- `x` → kick (`poor-cli/removeHostMember`)
- `p` → pass driver to this member (`poor-cli/handoffHostMember`)
- `c` → copy invite link for this member's role

### Data flow

1. On panel open: call `poor-cli/listHostMembers` + `poor-cli/listPresence` + `poor-cli/listRoomQueue`. Merge into a per-connection dict.
2. Subscribe to notifications (one-time at plugin init):
   - `poor-cli/memberTyping` → flip presence on matching row.
   - `poor-cli/queueUpdated` → refresh queue positions.
   - `poor-cli/collabMemberJoined`, `poor-cli/collabMemberLeft` (existing events) → refresh list.
3. Render via an autocommand on `BufWinEnter` for the panel buffer.

### Commands + keybinds

```
:PoorCLIUsers              " toggle panel
:PoorCLIUsers approve <id>
:PoorCLIUsers deny <id>
:PoorCLIUsers kick <id>
:PoorCLIUsers role <id> <role>
:PoorCLIUsers pass <id>
<leader>pu                 " toggle
```

### Tests (`users_panel_spec.lua`)

Use the plugin's existing test harness (plenary.nvim + mock RPC).

1. Panel opens with three mock members; rendering matches golden string.
2. Typing notification updates the target row.
3. `a` key approves a pending member.
4. Panel closes cleanly and unsubscribes.

### Acceptance criteria

- [ ] Panel is a fixed-width (32 cols) vertical split, closable.
- [ ] All quick actions fire the correct RPC.
- [ ] No RPC calls happen when the panel is closed (subscriptions survive; polling does not).

---

## Agent 8B: Typing + attribution in chat panel

### Goal

Replace the generic `user:` / `assistant:` prefixes in the chat panel with per-user attribution when multiplayer is active. Add a compact "typing" footer showing the currently-typing users.

### Design

1. **New file `nvim-poor-cli/lua/poor-cli/chat_attribution.lua`** exports:
   - `format_author(event) -> string` — takes a notification payload with `authorConnectionId` + `authorDisplayName` and returns the inline prefix (e.g. `alice ›`).
   - `format_typing_footer(presence_snapshot) -> string | nil` — returns `"alice and bob are typing…"` or nil.
2. **Modify `chat.lua`**:
   - When appending a chat chunk, look for the new author fields. If present and the author differs from the local user, render `<author> ›` prefix instead of the default role label.
   - Add a one-line footer at the bottom of the panel (below the input area) that shows `format_typing_footer(...)`. Empty when nobody is typing.
   - On each keystroke in the input buffer, debounce + send `poor-cli/setTyping { typing: true }`; on idle for 2s or submit, send `poor-cli/setTyping { typing: false }`.
3. **Fallback**: if attribution fields are absent (single-player), use the existing role labels unchanged.

### Keymap

No new keymaps. Attribution is automatic.

### Tests

1. Two-user session: alice's turn renders with `alice ›` prefix; bob sees it correctly.
2. Typing footer shows correct user list; clears on idle.
3. Single-player session: no visual change.

### Acceptance criteria

- [ ] Zero-config fallback for single-player users.
- [ ] Typing debounce respects `config.multiplayer.typingPresence.debounceMs`.
- [ ] No rpc spam — at most 1 `setTyping` per 250ms per user.

---

## Agent 8C: Diff-review voting

### Goal

Let multiple reviewers vote on each hunk. Votes appear inline in the existing diff review pane. Apply/reject only when threshold is met.

### Design

1. **New file `nvim-poor-cli/lua/poor-cli/diff_voting.lua`** exports:
   - `render_vote_row(hunk_id, votes, status, threshold) -> string[]` — returns lines like `votes: ✓ alice, carol · ✗ bob · pending (majority)` or `votes: ✓ 3/3 · approved`.
   - `vote(hunk_id, decision)` — calls `poor-cli/voteOnHunk`.
2. **Modify `diff_review.lua`**:
   - Before each hunk render, insert the vote row from `render_vote_row(...)`.
   - Add keymaps on hunk-focused rows:
     - `va` → approve hunk (`vote(id, "approve")`)
     - `vr` → reject hunk (`vote(id, "reject")`)
     - `vc` → clear own vote (calls `poor-cli/voteOnHunk { decision: "clear" }` — backend 7D treats clear as removal)
   - On `poor-cli/hunkVoteUpdated` notification, refresh the affected hunk row.
   - Existing `a` (accept) key: disabled on pending-vote hunks; shows a toast `"needs vote threshold"`.
3. **Status coloring**:
   - `approved` — accent green
   - `rejected` — accent red
   - `pending` — muted

### Tests

1. Two approvals + one rejection in majority mode → approved.
2. Accept keymap blocked when pending.
3. Vote row refreshes on `hunkVoteUpdated`.

### Acceptance criteria

- [ ] All three vote keymaps work.
- [ ] Owner-only threshold preserves pre-change behavior (`a` always works).
- [ ] Clear vote correctly removes user from tally.

---

## Integration checklist

By end of W8, the following Neovim user journeys must work:

1. Room of 3 users; alice types → bob + carol see "alice is typing…" in chat footer.
2. Alice submits a turn → bob's chat panel shows `alice ›` prefix for the message.
3. Bob submits a turn while alice's still streaming → both turns land in the transcript in order; queue panel shows bob's turn pending.
4. Agent produces an edit → all three see the diff review pane → each casts a vote → `va` on alice and bob triggers majority approval → hunk applies.
5. New viewer joins mid-session → users panel shows them pending → alice presses `a` to approve → viewer promoted.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| RPC notification storm overwhelms Neovim event loop | Debounce typing footer refresh to 200ms; batch queue snapshots |
| Users panel gets out of sync if subscription is dropped | On focus-gain, re-fetch `listHostMembers` + `listPresence` |
| Vote row adds too much visual noise for single-reviewer sessions | Hide vote row entirely when `threshold == "owner_only"` |

## Acceptance criteria (wave-level)

- [ ] All three integration journeys work end-to-end with a live backend (W7 features on).
- [ ] Feature-flag-off sessions render identically to pre-change.
- [ ] Plenary test suite green.
