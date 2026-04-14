# Phase Go 04 — Streaming Markdown Tokenizer & Renderer

**Priority:** The project's technical centerpiece. A correct, flicker-free streaming markdown renderer is the single biggest visual differentiator from a naive Glamour-based client.
**Agents:** 4 (4A ∥ 4B ∥ 4D in parallel; 4C waits on 4A + 4B)
**Dependencies:** Wave 0
**Philosophy:** Emit events, never strings. Commit decisions only when they cannot be retroactively invalidated. Accept partial input one byte at a time. The renderer is always ready to show partial output without re-rendering the whole buffer.

---

## Why we need this

Glamour renders full markdown documents on each call. During streaming at 50–200 tokens/sec, that means 50–200 full-buffer renders per second, with the entire rendered paragraph re-wrapped, re-highlighted, and reprinted. Visible flicker. High CPU. Stuttering cursor.

Codex CLI, Claude Code, ADA, and Clockwork do not use full-buffer re-render. They tokenize incrementally, emit events, and paint only the growing edge. This phase builds that stack.

---

## Design overview

Three layers, composed top-down:

```
bytes →  BlockTokenizer  →  RawLineEvents  →  InlineTokenizer  →  InlineEvents  →  Renderer  →  styled terminal text
         (Agent 4A)                          (Agent 4B)                           (Agent 4C)
                                                                                    uses
                                                                                  Highlighter (Agent 4D)
```

- **BlockTokenizer**: byte stream → sequence of `BlockOpen`, `BlockClose`, `RawLine`, `Commit` events.
- **InlineTokenizer**: per-line → sequence of `InlineOpen`, `InlineClose`, `Text`, `Link` events.
- **Renderer**: event streams → styled output; tracks commit marks so the chat widget can paint only the tail.
- **Highlighter**: chroma wrapper used by Renderer for code-fence content.

Key concept: **the commit mark**. Every `CommitEvent` says "everything emitted before this is finalized and will not change." The chat widget saves the mark, and asks only for the tail since last mark on the next frame.

---

## File-scope table

| Agent | Creates | Modifies |
|-------|---------|----------|
| 4A    | `internal/markdown/block.go`, `internal/markdown/events.go` (partial — block types), `internal/markdown/block_test.go` | — |
| 4B    | `internal/markdown/inline.go`, `internal/markdown/events.go` (add inline types — 4A lands first) | — |
| 4C    | `internal/markdown/renderer.go`, `internal/markdown/stream.go`, `internal/markdown/renderer_test.go`, `internal/markdown/stream_test.go` | — (depends on events.go as final) |
| 4D    | `internal/markdown/highlight.go`, `internal/markdown/highlight_test.go` | — |

### Intra-phase collisions

- **`internal/markdown/events.go`** — shared by 4A (block events) and 4B (inline events). Both modify the same file.

### Proposed sub-waves

- **Sub-wave α (4A ∥ 4D)** — 4A creates `events.go` with block types + `BlockKind` / `InlineKind` enums (defined together for consistency); 4D is independent.
- **Sub-wave β (4B)** — 4B adds inline event types to `events.go` after 4A is merged.
- **Sub-wave γ (4C)** — 4C composes everything.

Sub-waves can be tightened if 4A delivers a complete `events.go` (block + inline) up front and 4B only fills in inline behavior — in which case 4B does not touch `events.go` at all.

---

## Event model (shared — part of 4A deliverable, amended by 4B)

```go
package markdown

type BlockKind uint8
const (
    BlockParagraph BlockKind = iota
    BlockHeading1
    BlockHeading2
    BlockHeading3
    BlockHeading4
    BlockHeading5
    BlockHeading6
    BlockCodeFence
    BlockBlockquote
    BlockListUnordered
    BlockListOrdered
    BlockListItem
    BlockThematicBreak
)

type InlineKind uint8
const (
    InlineEmphasis InlineKind = iota
    InlineStrong
    InlineCode
    InlineLink
    InlineAutolink
)

type EventKind uint8
const (
    EventBlockOpen EventKind = iota
    EventBlockClose
    EventRawLine
    EventInlineOpen
    EventInlineClose
    EventText
    EventLink
    EventCodeBlockDelta
    EventCommit
)

type Event interface { Kind() EventKind }

type BlockOpenEvent struct {
    Block BlockKind
    Info  string // code-fence info string, list ordered-start marker
    Line  int
}
func (BlockOpenEvent) Kind() EventKind { return EventBlockOpen }

type BlockCloseEvent struct { Block BlockKind; Line int }
func (BlockCloseEvent) Kind() EventKind { return EventBlockClose }

// RawLine carries a block's raw text for the inline tokenizer to process.
// It is NOT emitted to the renderer directly — the Streamer consumes it and
// passes it through InlineTokenizer first.
type RawLineEvent struct {
    Block BlockKind
    Text  string
    Line  int
}
func (RawLineEvent) Kind() EventKind { return EventRawLine }

type InlineOpenEvent  struct { Inline InlineKind }
type InlineCloseEvent struct { Inline InlineKind }
type TextEvent        struct { Value string }
type LinkEvent        struct { Text, URL string }

// CodeBlockDelta is emitted for lines inside a code fence.
// The renderer applies syntax highlighting per line.
type CodeBlockDeltaEvent struct { Lang, Line string; Final bool }

// Commit marks a point before which all emitted events are finalized.
// Renderer saves the mark so the chat widget can request "tail since commit N".
type CommitEvent struct { Mark uint64 }
```

---

## Agent 4A: Block tokenizer

### What to build

A byte-in, event-out incremental tokenizer that:
1. Receives arbitrary chunks of bytes via `Write`.
2. Emits block-level events as soon as decisions are safe.
3. Never backtracks past a 256-byte lookahead window.
4. Never emits speculatively (no "tentative" events that might be rewritten).

### API

```go
package markdown

type BlockTokenizer struct { /* ... */ }

func NewBlockTokenizer() *BlockTokenizer
func (b *BlockTokenizer) Write(chunk []byte)
func (b *BlockTokenizer) Drain() []Event
func (b *BlockTokenizer) Close() []Event
```

### State

```go
type blockState struct {
    buf         []byte        // unconsumed bytes
    line        int           // current line number
    open        []BlockKind   // stack of open blocks (outermost first)
    codeInfo    string        // current code-fence info string, if in code
    paragraphBuf strings.Builder  // accumulating paragraph text
}
```

### Decision rules (per scanned position)

For each newline found in the buffer, we have a full line to classify. The scanner advances line-by-line and emits events as decisions firm up.

#### At start of line

1. **Code fence state check**: if `open` top is `BlockCodeFence`, the line is either the closing fence (`^\`\`\`\s*$`) or raw code content.
2. **Leading whitespace**: strip up to 3 leading spaces (CommonMark). 4+ spaces in a non-list context → indented code block (out of scope for v1; treat as paragraph).
3. **Check block markers in priority order**:
   - `^\s*$` → blank line → closes any open paragraph; commit mark if at depth 0.
   - `^---$` or `^***$` or `^___$` → thematic break.
   - `^#+ ` (1–6 hashes then space) → heading.
   - ` ^\`\`\`` or `^~~~` followed by optional info → open code fence.
   - `^> ` → blockquote (recursive; out of scope v1 → treat as paragraph with `> ` prefix stripped).
   - `^- ` / `^* ` / `^+ ` → unordered list item.
   - `^\d+\. ` → ordered list item.
   - Otherwise → paragraph line.

#### Commit rules

- **Paragraph commits** on blank line or end of input.
- **Heading commits** immediately on its own newline.
- **Code fence commits** on the closing fence.
- **List item commits** on the next line that is not a continuation line.
- **Thematic break commits** immediately.

Only when a block is committed does the tokenizer emit its `BlockOpenEvent` + `RawLineEvent`s + `BlockCloseEvent`. Before commit, the events stay in a pending buffer.

#### Why not emit earlier?

Consider: `# Title\n` then later `\n---` arriving — the `---` would make `# Title` a setext heading (in full CommonMark). We don't support setext, so for our subset, we can emit ATX headings immediately.

Consider: `*foo` arriving. Is it a list item or the start of an emphasis? If next char is space → list; else → paragraph. We need ≥1 byte of lookahead.

Consider: `- item one\n- item two\n  continuation\n\n` — the list closes on the blank line, not before. Emitting `BlockListClose` after `- item two\n` would be wrong if a continuation follows.

**Rule of thumb**: emit when the next rule you'd apply is unambiguous given the current state + ≤1 byte of lookahead. If not: hold.

### Holdback buffer

Cap unemitted buffer at 256 bytes per open block. If buffer grows larger (unlikely for well-formed input), emit pending content as a paragraph to avoid unbounded memory.

### Close semantics

`Close()` signals no more bytes. Force-close all open blocks:
- Paragraph → commit immediately.
- Code fence → close without a closing fence; emit a `BlockCloseEvent` with no error (renderer is tolerant).
- Lists → close on last item.

### Tests (`block_test.go`)

For each scenario below, feed the full input, then the same input split randomly at every byte boundary, and assert identical event streams.

| # | Input | Expected events |
|---|-------|-----------------|
| 1 | `hello world\n` | BlockOpen(Paragraph), RawLine(Paragraph,"hello world"), BlockClose(Paragraph), Commit |
| 2 | `# Heading\n` | BlockOpen(Heading1), RawLine, BlockClose, Commit |
| 3 | `# One\n## Two\n` | H1 open+close, H2 open+close, Commit |
| 4 | ` `\`\`\`go\nfmt.Println()\n\`\`\`\n ` | BlockOpen(CodeFence, info="go"), CodeBlockDelta("go","fmt.Println()"), BlockClose(CodeFence), Commit |
| 5 | `- a\n- b\n\n` | BlockOpen(ListUnordered), two BlockListItem open+close, BlockClose(ListUnordered), Commit |
| 6 | `para\n\nmore para\n` | two paragraphs |
| 7 | `---\n` | ThematicBreak |
| 8 | Fuzz: a 2 KB canonical doc split at every single byte boundary | identical event stream regardless of split |

Plus a property-based test using `testing/quick`: random valid markdown docs up to 1 KB, split randomly, must produce the same events as the unsplit version.

### Acceptance criteria

- [ ] All scenario tests pass.
- [ ] Split-invariance property holds over 10,000 random seeds.
- [ ] Memory usage bounded: ≤ 256 bytes per open block in the pending buffer.
- [ ] No allocations for lines <64 bytes (benchmarked).
- [ ] Close() is idempotent after the first call.

### Decisions locked

- Setext headings: NOT supported (require unbounded lookahead).
- Blockquote recursion: NOT supported in v1; strip the leading `> ` marker and render the content as a muted paragraph.
- 4-space indented code blocks: NOT supported.
- Tab handling in list continuations: convert tabs to 4 spaces for width calculations.

---

## Agent 4B: Inline tokenizer

### What to build

Consumes `RawLineEvent` bodies from the block tokenizer; emits inline events for emphasis, strong, code spans, and links. Streaming-aware: holds back bytes until context is disambiguous.

### API

```go
package markdown

type InlineTokenizer struct { /* ... */ }

func NewInlineTokenizer() *InlineTokenizer

// FeedLine processes one block-text line. Returns the events for this line.
// Typically Text, InlineOpen, InlineClose, Link interleaved.
func (i *InlineTokenizer) FeedLine(rawLine RawLineEvent) []Event

// Close flushes any unclosed inline context as literal text.
func (i *InlineTokenizer) Close() []Event
```

### Recognized inline syntax

| Syntax | Emit |
|--------|------|
| `*text*` or `_text_` | InlineOpen(Emphasis), Text, InlineClose(Emphasis) |
| `**text**` or `__text__` | InlineOpen(Strong), Text, InlineClose(Strong) |
| `***text***` | nested InlineOpen(Strong), InlineOpen(Emphasis), Text, close, close |
| `` `code` `` | InlineOpen(Code), Text(literal), InlineClose(Code) |
| `[text](url)` | LinkEvent{Text, URL} (single event, pre-resolved) |
| `<url>` | LinkEvent (autolink) |
| everything else | TextEvent |

### Out of scope (v1)

- Images (`![alt](url)`) — render as literal for now.
- Raw HTML.
- Hard line breaks (trailing two spaces) — treat as whitespace.
- Footnotes.
- Strikethrough (~~), tables, task lists — optional extensions; can be added in Wave 6.

### Flanking rules (CommonMark §6.4, simplified)

A `*` opens emphasis if preceded by whitespace/start and followed by non-whitespace. It closes emphasis if preceded by non-whitespace and followed by whitespace/end. Ambiguous positions require lookahead.

Simplified algorithm:
1. Scan left-to-right.
2. Maintain a stack of "open delimiters" (each with position, type, length).
3. On closer candidate: pop matching opener from stack; emit matching Open/Close events with the enclosed text.
4. Unmatched openers at end-of-line → flush as literal text.

### Holdback buffer

Per line, hold up to 128 bytes after seeing an unclosed inline opener. If the line ends or buffer fills without closing, emit as literal.

Streaming note: the block tokenizer delivers one `RawLineEvent` per line only after the line is known-complete. So inline tokenizer never sees partial lines. Holdback is therefore bounded by line length, not by streaming boundaries.

### Tests (`inline_test.go`)

Minimum 30 cases covering CommonMark canonical examples. Priority order:

| # | Input | Expected |
|---|-------|----------|
| 1 | `hello` | Text("hello") |
| 2 | `*em*` | Open(Emph), Text("em"), Close(Emph) |
| 3 | `**strong**` | Open(Strong), Text("strong"), Close(Strong) |
| 4 | `***both***` | Open(Strong), Open(Emph), Text("both"), Close(Emph), Close(Strong) |
| 5 | `a *b* c` | Text("a "), Open(Emph), Text("b"), Close(Emph), Text(" c") |
| 6 | `a*b*c` | ambiguous — depending on flanking, either all literal or emphasis; match CommonMark spec (emphasis) |
| 7 | `` `code` `` | Open(Code), Text("code"), Close(Code) |
| 8 | `[x](y)` | Link{Text:"x", URL:"y"} |
| 9 | `[x`  end of line | Text("[x") — unclosed link falls back literal |
| 10 | `<https://example.com>` | Link autolink |
| 11 | `*unclosed` end of line | Text("*unclosed") |
| 12 | `*em\n*more\n*close*` handed as separate lines | three lines each independent |
| ... | ... | ... |

### Acceptance criteria

- [ ] All canonical CommonMark emphasis tests pass (at least the "safe" subset — see commonmark spec §6.4 reference implementation).
- [ ] Unclosed inline degrades to literal without panicking.
- [ ] Line boundary: inline state does not leak across lines (each FeedLine is independent).

### Decisions locked

- Strikethrough (GFM extension): NOT enabled in v1.
- Autolink mode: strict `<url>` form only. No URL detection in plain text.

---

## Agent 4C: Stream renderer

### What to build

The renderer consumes block + inline events from a `Streamer` and produces terminal-styled output. It maintains an internal segment list with commit marks so the chat widget can request only the delta since the last render.

### API

```go
package markdown

// Segment is a unit of renderable output.
type Segment struct {
    Text  string   // styled (ANSI escape sequences embedded)
    Plain string   // unstyled text, for width / scroll math
    Width int      // display width of Plain
}

type Mark uint64

// Renderer consumes events and produces styled output.
type Renderer struct { /* ... */ }

type RendererDeps struct {
    Theme       *theme.Theme
    Highlighter *Highlighter
    Width       int
}

func NewRenderer(d RendererDeps) *Renderer
func (r *Renderer) Feed(events []Event)
func (r *Renderer) Full() string
func (r *Renderer) TailSince(mark Mark) (tail string, newMark Mark)
func (r *Renderer) Resize(width int)

// Streamer is the top-level facade: bytes in, events + rendered string out.
type Streamer struct { /* ... */ }

func NewStreamer(d RendererDeps) *Streamer
func (s *Streamer) Write(chunk []byte)
func (s *Streamer) Drain() (events []Event, full string)
func (s *Streamer) TailSince(mark Mark) (tail string, newMark Mark)
func (s *Streamer) Full() string
func (s *Streamer) Resize(width int)
func (s *Streamer) Close() (tail string)
```

### Internal model

```go
type renderer struct {
    theme     *theme.Theme
    hl        *Highlighter
    width     int
    segments  []Segment
    commits   []Mark        // parallel array of "segment up-to commit"
    nextMark  Mark
    openBlock BlockKind     // currently open block
    codeLang  string
    codeBuf   []string      // code-fence buffered lines
}
```

When a BlockOpenEvent arrives: push styling context.
When RawLineEvent → inline tokenize → render to segments.
When CodeBlockDeltaEvent → highlight + append segment.
When BlockCloseEvent: pop context.
When CommitEvent: record current len(segments) against the mark.

### Rendering rules per block

**Paragraph**: simple text with word-wrap at Width. Style: Base.
**Heading1..6**: bold, sized down by level, trailing blank line. Style: Base + Bold + color gradient (H1 bright, H6 muted).
**Code fence**: gutter `│ ` + highlighted content. Language badge on open line: `╭─ go ────────────`. Closing: `╰─────────────────`.
**Blockquote**: `│ ` prefix per line, Muted color.
**List**: `• ` for unordered, `1. ` for ordered. Nested indentation 2 spaces per level (v1: single-level only).
**Thematic break**: `───────` full-width, Muted.

### Diff-painting protocol

The chat widget's streaming message tracks a `Mark`. After each event drain:
1. Chat widget calls `TailSince(prevMark)` → returns `(tail, newMark)`.
2. Chat widget appends `tail` to its rendered buffer in place.
3. Chat widget stores `newMark` for next frame.

Key rule: `tail` must be ANSI-safe — never cut an escape sequence mid-sequence. Segments are always whole; tail composes whole segments.

### Wrapping

Wrap at `width - 2` (reserve for potential border). Use `go-runewidth` for column math. Preserve ANSI escapes during wrap (track "open styles" at each wrap point and re-emit at start of next visual line).

### Code-fence streaming rule

Within a code fence, highlight **the in-progress (last) line only** on each feed. Earlier lines freeze. When the fence closes, re-highlight the full block once in case multi-line context changes how the first line is colored (rare but possible).

Actually: simpler rule that avoids multi-line context is to highlight line-by-line from the start and never retroactively re-highlight. Chroma handles most languages fine line-by-line except for multi-line strings. Trade-off: minor visual glitches on Python triple-quoted strings vs. no flicker. Choice: line-by-line default, flag to enable end-of-block re-highlight.

### Tests (`renderer_test.go` and `stream_test.go`)

1. Golden output for each block type (paragraph, heading, code fence Go/Python/JSON, list, blockquote).
2. Wrapping correctness at width 60, 80, 120, 200.
3. Stream a 4 KB markdown document byte-by-byte:
   - `Full()` at end equals full-document render.
   - `TailSince(prevMark)` returns monotonically-increasing output.
   - No ANSI escape appears split across two `TailSince` calls.
4. Resize mid-stream: rendered output re-wraps without corruption.
5. Unicode correctness (CJK, emoji, combining marks).

### Acceptance criteria

- [ ] Zero import of `github.com/charmbracelet/glamour`.
- [ ] 60 Hz render at 200 tok/s with no dropped frames (measured in Wave 6D).
- [ ] Tail-paint correctness: never cuts ANSI escapes.
- [ ] Resize handling is correct without re-feeding bytes.
- [ ] `go test -race` clean.

### Decisions locked

- Heading color gradient: H1 brightest (accent), H2–H3 accent-muted, H4–H6 base text with bold. Minimal differentiation — headings are already a rarity in ADA-minimal chat output.
- Code-fence gutter character: `│` (U+2502).
- Re-highlight code blocks at close: OFF. Accept minor multi-line-string color glitches in exchange for zero re-render cost.
- Maximum segment count before renderer forces a coalesce: 10,000.

---

## Agent 4D: Chroma integration

### What to build

A thin wrapper around chroma that:
- Maps language info strings to chroma lexers.
- Highlights one line at a time (for streaming code-fence lines).
- Highlights whole blocks (for committed code-fence finals).
- Falls back gracefully for unknown languages.
- Exposes a per-lang cache of lexers (chroma lexer resolution is cheap but not free).

### API

```go
package markdown

type Highlighter struct { /* ... */ }

func NewHighlighter(theme *theme.Theme) *Highlighter
func (h *Highlighter) HighlightLine(lang, line string) string   // returns styled string
func (h *Highlighter) HighlightBlock(lang, code string) string  // for whole blocks
```

### Language resolution

1. Try `chroma.Lexers.Get(lang)` for the declared info string (e.g. `go`, `python`, `js`).
2. If not found, try aliases (e.g. `golang` → `go`).
3. If still not found, use `chroma.Lexers.Fallback` or plain pass-through.

Cache resolved lexers in `map[string]chroma.Lexer`.

### Style mapping

Chroma produces tokens with `chroma.TokenType`. Map token types to lipgloss styles:

| Token group | Style |
|-------------|-------|
| Comment | Muted italic |
| Keyword | primary brand color |
| String | secondary brand color |
| Number | Info |
| Function name | Focus |
| Type | Success (green-ish) |
| Operator | Base |
| Text | Base |

Concrete colors come from `theme.Theme` fields (add SyntaxKeyword, SyntaxString, SyntaxComment, etc. to the theme — coordinate with Agent 2B).

### Tests (`highlight_test.go`)

Golden outputs for:
1. Go: `fmt.Println("hello")`.
2. Python: `def hello(): print("hi")`.
3. JSON: `{"a": 1}`.
4. bash: `ls -la | grep foo`.
5. Unknown lang: passthrough unchanged.

### Acceptance criteria

- [ ] Lexer cache hit rate 100% on warm run.
- [ ] Fallback for unknown lang: plain text, no errors.
- [ ] Styles use theme tokens only; no hardcoded colors.

### Decisions locked

- Language aliases: support standard chroma aliases plus `golang`→`go`, `py`→`python`, `ts`→`typescript`, `sh`→`bash`, `rs`→`rust`.
- Chroma style: `monokai` for the dark theme; `friendly` for the light theme.

---

## Integration with chat widget (Wave 3A)

The chat widget sees `markdown.Streamer` as the interface. Per in-flight assistant message:

```go
// In chat widget
type streamingMsg struct {
    requestID string
    streamer  *markdown.Streamer
    mark      markdown.Mark
    rendered  []string  // rendered segments, appended tail each frame
}

func (c *ChatView) appendChunk(requestID, chunk string) {
    m := c.findStreaming(requestID)
    m.streamer.Write([]byte(chunk))
    _, _ = m.streamer.Drain()          // discard events — renderer already consumed
    tail, newMark := m.streamer.TailSince(m.mark)
    m.rendered = append(m.rendered, tail)
    m.mark = newMark
}

// On stream end
func (c *ChatView) endStream(requestID string) {
    m := c.findStreaming(requestID)
    tail, newMark := m.streamer.Full(), m.streamer.Mark() // optional: full re-render for final consistency
    _ = tail; _ = newMark
}
```

---

## Performance targets

Measured on an M-series MacBook:

| Scenario | Target |
|----------|--------|
| Block tokenizer throughput | ≥ 50 MB/s |
| Inline tokenizer throughput | ≥ 30 MB/s |
| Renderer first paint (1 KB doc) | ≤ 1 ms |
| Tail render per chunk (200 chars) | ≤ 0.1 ms |
| Total pipeline at 200 tok/s stream | ≤ 10% of a single core |

These are measured by Wave 6D (benchmarks). The design should hit them comfortably; if it does not, profile first.

---

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Chroma's lexer cannot tokenize partial input correctly | Medium | Per-line highlight sidesteps; flag for end-of-block re-highlight for pathological languages |
| CommonMark emphasis rules are subtle — we ship bugs | High | Adopt a conservative subset; exhaustive test suite; degrade to literal on ambiguity |
| Multi-byte UTF-8 at chunk boundary breaks tokenizer | Medium | Never cut multi-byte chars; hold incomplete trailing bytes in buffer until next Write |
| Tail-paint accidentally cuts ANSI escape | Low | Segment model guarantees whole segments only |
| Memory leak on very long streams (never commits) | Low | Paragraph commit on blank line; enforce max-block-size 1 MB → force commit |

---

## Summary

This wave is intentionally the most ambitious. It's also the most bounded: pure input-output, no network, no UI state, no external APIs. Agents 4A and 4B can be written from the CommonMark spec + the test table in this document. Agent 4C composes them with theme + chroma. Agent 4D is a 150-line chroma wrapper.

If you only remember two things from this doc:
1. **Emit events only when they cannot be retroactively invalidated.**
2. **The renderer maintains a commit mark so the chat widget repaints only the tail.**
