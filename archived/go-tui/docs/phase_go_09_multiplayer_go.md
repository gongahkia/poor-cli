# Phase Go 09 — Go Client Multiplayer UI

**Priority:** Bring parity with Neovim (W8) in the Go TUI. ADA-minimal rules throughout: no boxes, no flashy color changes, every new surface fits into ≤2 extra screen lines when possible.
**Agents:** 3 (all parallel, disjoint files)
**Dependencies:** Wave 5 (flows) AND Wave 7 (backend features). Can run in parallel with Wave 8 (Neovim) once W7 lands.
**Philosophy:** Do not add chrome. Users panel is a toggleable right rail, not a fourth permanent pane. Typing + attribution use inline text only. Voting appears inline in the diff modal, no new modal stack.

---

## Style constraints (explicit — do not deviate)

- **No new persistent panes.** The transcript + input + status line remain the only permanent visual regions. The users panel is an optional, toggled, right-hand rail (same visual weight as the transcript — no border between).
- **No emoji or icons** beyond single muted unicode glyphs (`●`, `◌`, `›`, `·`) already used elsewhere.
- **No color changes outside the existing token set.** Presence/votes/attribution map onto Muted / Focus / Success / Error tokens.
- **No modal overlays for presence.** Typing indicators are inline footer text, not popups.
- **No animations** beyond the existing 60 Hz render loop. No blink, no pulse.

---

## File-scope table

| Agent | Creates | Modifies |
|---|---|---|
| 9A | `internal/tui/widgets/users_panel.go`, `internal/tui/widgets/users_panel_test.go`, `internal/tui/flows/users.go`, `internal/tui/flows/users_test.go` | `internal/tui/app.go` (toggle + region), `internal/tui/regions.go` (right-rail math), `internal/protocol/multiplayer.go` (new types — may already exist from W7 trailer edit; add if missing) |
| 9B | `internal/tui/flows/presence.go`, `internal/tui/flows/attribution.go`, `internal/tui/flows/presence_test.go` | `internal/tui/widgets/chat.go` (author prefix render), `internal/tui/widgets/statusbar.go` (typing footer slot), `internal/tui/flows/chat.go` (forward author fields to state) |
| 9C | `internal/tui/flows/voting.go`, `internal/tui/flows/voting_test.go` | `internal/tui/flows/diff.go` (vote row render + keymaps) |

### Intra-phase collisions

- **`internal/tui/app.go`** — 9A only. Other agents do not touch it.
- **`internal/tui/widgets/chat.go`** — 9B only.
- **`internal/tui/flows/diff.go`** — 9C only.

No collisions. All three agents parallel-safe.

---

## Agent 9A: Users panel (right rail)

### Goal

A toggleable right rail showing every room member with role, approval, presence, and vote counts. Opened via `/users` slash command or the configured keybind (default `ctrl+u`). Width: 28 cols. When open, the transcript reflows to `width - 28 - 1` (one-column gap). When closed, the rail is entirely absent — no vestigial border.

### Visual spec

```
 users · 4
 alice     owner
           ● typing
 bob       prompter
           #3 queue
 carol     prompter
           voted 2/3
 dave      viewer
           pending
```

- Each member is two rows: name+role on top, presence/status in muted below.
- No borders. No background fills.
- Role text is muted; name is base. "Pending" is accent-warn; "typing" is accent-focus.
- Vertical scrollable if more members than available height.

### Flow wiring (`internal/tui/flows/users.go`)

Subscriptions:
- `poor-cli/memberTyping` → `state.ActionUpdateMemberTyping`
- `poor-cli/queueUpdated` → `state.ActionUpdateQueue`
- `poor-cli/collabMemberJoined`, `poor-cli/collabMemberLeft` → refresh member list

Actions on selection (keybinds when rail is focused):
- `a` → `poor-cli/approveHostMember`
- `d` → `poor-cli/denyHostMember`
- `x` → `poor-cli/removeHostMember`
- `r` → open role picker modal (existing modal pattern)
- `p` → `poor-cli/handoffHostMember`
- `enter` → focus prompter (if multi-prompter: no-op; if single-prompter: same as pass driver)

### State additions

Extend `internal/state/types.go` with:

```go
type MultiplayerState struct {
    Enabled     bool
    RoomName    string
    Members     []Member
    Typing      map[string]bool        // connectionId → typing
    Queue       []QueueItem
    PresenceAt  time.Time              // last presence snapshot
}

type Member struct {
    ConnectionID    string
    DisplayName     string
    Role            string
    ApprovalState   string
    HandRaised      bool
    QueuePosition   int
    VotesCast       int
    VotesPending    int
}
```

### Keybinds (config)

Add to default `Keymap`:
- `focus.users = ctrl+u` — toggle + focus rail
- `users.approve = a`
- `users.deny = d`
- `users.kick = x`
- `users.role = r`
- `users.pass = p`

### Tests

1. Golden render test at width 120 with 4 members; panel occupies right 28 cols.
2. Typing notification flips indicator.
3. Panel closed when multiplayer disabled (never renders).

### Acceptance criteria

- [ ] Closed panel leaves zero footprint (transcript spans full width).
- [ ] Open/close toggle is single keypress.
- [ ] All quick actions fire correct RPC and show a status-line toast on success/failure.

---

## Agent 9B: Presence + attribution

### Goal

When multiplayer is active, prefix chat messages with the author's display name. Show a one-line typing footer above the status bar.

### Attribution

Minimal visual rule: when `authorDisplayName` is present and differs from the local user, render the first line of the assistant message as:

```
poor-cli · replying to alice
  autumn wind arrives
  scattering leaves across
  the cold morning path
```

When the author IS the local user (or multiplayer disabled), keep the existing `poor-cli` prefix alone.

User turns:
```
alice › write me a haiku
```

Local user's own turn:
```
you › write me a haiku
```

Never combine: a user never sees `alice ›` for their own turn.

### Typing footer

A single row between the input area and the bottom status bar:

```
  alice is typing…
```

- Present only when someone other than the local user is typing.
- When multiple: `alice and bob are typing…`; more than three: `alice, bob, carol +1 typing…`.
- Text style: muted. No color beyond muted. No ellipsis blink.

### Flow wiring (`internal/tui/flows/presence.go`)

- Subscribe to `poor-cli/memberTyping` → dispatch `state.ActionUpdateMemberTyping`.
- On user keystroke in the input widget (hook into Wave 3B emit): call `poor-cli/setTyping { typing: true }` debounced to every 250ms.
- On 2s idle or on Submit: call `poor-cli/setTyping { typing: false }`.

### Flow wiring (`internal/tui/flows/attribution.go`)

- On `poor-cli/streamChunk` and friends (already subscribed in W5 chat flow), inspect `authorConnectionId` + `authorDisplayName` and forward to state.
- Chat widget uses those fields when rendering message header.

### Tests

1. Local user keystroke → one `setTyping` call per debounce window.
2. Remote typing notification → footer updates.
3. Attribution prefix appears for remote-authored messages only.

### Acceptance criteria

- [ ] Typing footer is exactly one row tall; absent when nobody typing.
- [ ] Attribution adds at most one line per message.
- [ ] No regression for single-player mode.

---

## Agent 9C: Voting in diff modal

### Goal

Inline vote rows within the existing diff review modal. No new modal. Minimal visual weight.

### Visual spec

Before each hunk header, render one row:

```
  votes · ✓ alice, carol · ✗ bob · pending (majority)
```

When approved:
```
  votes · ✓ 3/3 · approved
```

When rejected:
```
  votes · ✗ 2/3 · rejected
```

Color: `✓` in Success token, `✗` in Error token, everything else Muted. When `threshold == "owner_only"`, hide the row entirely.

### Keybinds

Extend the existing diff review modal with:
- `va` — approve hunk (`poor-cli/voteOnHunk { decision: "approve" }`)
- `vr` — reject hunk (`poor-cli/voteOnHunk { decision: "reject" }`)
- `vc` — clear own vote (`poor-cli/voteOnHunk { decision: "clear" }`)

Disable the existing `y`/`n` accept keys on hunks with `status = pending` when voting is on. Show a one-time status-line toast: `"needs vote threshold"`.

### Flow wiring (`internal/tui/flows/voting.go`)

- Subscribe to `poor-cli/hunkVoteUpdated` → dispatch `state.ActionUpdateHunkVotes`.
- On vote keybind, send vote RPC + rely on notification for state update.

### Tests

1. Vote row renders correctly for each status.
2. `y` key blocked on pending; toast fires.
3. Clear vote removes user from tally on next notification.

### Acceptance criteria

- [ ] Vote row is exactly one line tall.
- [ ] Owner-only mode hides the row entirely.
- [ ] No color fills or boxes added to the diff modal.

---

## Integration checklist

By end of W9, these Go client user journeys work:

1. `ctrl+u` toggles the users panel; closed is the default.
2. Typing into the input triggers debounced presence broadcasts; others see the typing footer.
3. Chat messages from others render with `<name> ›` prefix; local messages say `you ›`.
4. Diff review shows vote rows; `va` approves, majority triggers apply.
5. Single-player session renders identically to W5 output — zero visual delta.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Users panel widens default layout and breaks <100-col terminals | Auto-hide if terminal width < 100 cols; toggle is a no-op in that case with a toast explanation |
| Attribution prefix bloats message headers | At most one line; truncate display name at 16 chars |
| Typing footer flicker from rapid on/off | Coalesce updates to a 100ms tick |

## Acceptance criteria (wave-level)

- [ ] All three Go agents land and CI is green.
- [ ] `make test` + `make test-race` clean.
- [ ] Single-player session unchanged vs. W5 golden.
- [ ] Multi-player session matches the five integration journeys above.
