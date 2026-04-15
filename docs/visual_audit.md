# Visual Audit

Scope: Agent 10A ADA-minimal audit. Captures are ANSI-stripped ASCII render states.

Checklist key: `no-box`, `no-fill`, `six-colors`, `labels`, `no-emoji`, `icons`, `gap`, `headers`.

## 1. Splash

```text
gocli-poor · repo:poor-cli · branch:main

ready.
› ·
ready
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 2. Empty chat

```text
gocli-poor · connected · anthropic

ready.
› ·
ready
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 3. First user turn in flight

```text
you › audit the tui

poor-cli › ·
› ·
waiting
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 4. Streaming mid-response

```text
you › audit the tui

poor-cli › checking widgets and flows
› ·
ready
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 5. Completed turn

```text
you › audit the tui

poor-cli › removed modal borders and filled backgrounds.
› ·
ready
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 6. Three-turn transcript

```text
you › list issues

poor-cli › palette, diff, permission.

you › fix them

poor-cli › done.
› ·
ready
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 7. Command palette

```text
› /c
› /compact  Compact transcript
  /clear    Clear transcript
  /cost     Show cost
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 8. Mention picker

```text
@chat
› src/chat.go
  internal/tui/chat.go
  docs/chat.md
package chat
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 9. Provider picker

```text
provider
› anthropic        claude-sonnet       [ready]
  openai           gpt-5               [ready]
  ollama           llama-local         [miss ]
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 10. Session picker

```text
session
› audit polish               12 msgs  claude
  launch notes                4 msgs  gpt-5
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 11. Diff review, single hunk

```text
pending edits · 1
› internal/foo.go  +3 -1

diff · internal/foo.go · 1/1
@@ -1,3 +1,4 @@
+import "fmt"
 scroll all
[y] accept hunk  [n] reject  [r] regen
[Y] accept all   [N] reject all
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 12. Diff review, multiple hunks

```text
pending edits · 3
› internal/foo.go  +3 -1
  README.md  +1 -0
  internal/bar.go  +0 -2

diff · internal/foo.go · 2/3
@@ -9,3 +9,4 @@
+return nil
 scroll 8/21
[y] accept hunk  [n] reject  [r] regen
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 13. Permission prompt

```text
permission · 20s
tool · bash
why · install dev dependency

cmd
  npm install -D vitest

[a] once  [s] session
[p] always  [d] deny  [esc] deny
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 14. API key prompt

```text
api key
anthropic needs an API key

api key
____

✓ keyring

[enter] save  [esc] cancel
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 15. Cost modal

```text
cost
turn         $0.0083
session      $0.0472
input        12,834
output       2,104
cache read   8,222
cache write  4,190
anthropic    $0.0412
savings      $0.0134 (22%)
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 16. Users panel

```text
users · 2
› alice          prompter
  ● typing
  bob            viewer
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 17. Error toast

```text
gocli-poor · repo:poor-cli · branch:main
you › run tests

poor-cli › command failed
› ·
error: test failed
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 18. Success toast

```text
gocli-poor · repo:poor-cli · branch:main
you › save key

poor-cli › saved.
› ·
saved
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 19. Resize 60 cols

```text
gocli-poor · repo:poor-cli · branch:main
you › summarize

poor-cli › compact output remains flush.
› ·
ready
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 20. Resize 200 cols

```text
gocli-poor · repo:poor-cli · branch:main
you › summarize

poor-cli › wide output remains text-only with no panel fill, border, or decorative rail.
› ·
ready
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 21. Tool block collapsed

```text
poor-cli › checking workspace
› bash · running
  args: git status --short
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## 22. Tool block expanded

```text
poor-cli › checking workspace
· bash · done
  args: git status --short
  output:
    clean
```

check: green no-box | green no-fill | green six-colors | green labels | green no-emoji | green icons | green gap | green headers

## Changes

- Added `internal/tui/widgets/flush.go` for flush headers and lists.
- Removed modal, palette, input, diff, permission, markdown code, blockquote, and thematic-rule box drawing.
- Removed built-in filled backgrounds and collapsed theme output to Base, Muted, Focus, Success, Error, Warning color values.
- Replaced disallowed glyphs with `›`, `·`, `✓`, `✗`, `●`, `◌`, or plain ASCII.
- Enforced one blank line between chat messages.
- Updated affected markdown/theme golden snapshots and tests.

## Verification

```text
go test ./internal/...
go test -tags=e2e -run FixtureReplay ./test/e2e/...
```

result: green.
