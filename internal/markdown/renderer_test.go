package markdown

import (
	"strings"
	"testing"

	"github.com/gongahkia/gocli-poor/internal/theme"
)

func TestRendererGoldenBlocks(t *testing.T) {
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	width := 40
	tests := []struct {
		name string
		in   string
		want string
	}{
		{
			name: "paragraph",
			in:   "hello *world* and **friends**\n",
			want: "hello world and friends\n",
		},
		{
			name: "heading",
			in:   "# Title\n",
			want: "Title\n\n",
		},
		{
			name: "go code fence",
			in:   "```go\nfmt.Println(1)\n```\n",
			want: codeFencePlain("go", []string{"fmt.Println(1)"}, width),
		},
		{
			name: "python code fence",
			in:   "```python\nprint('x')\n```\n",
			want: codeFencePlain("python", []string{"print('x')"}, width),
		},
		{
			name: "json code fence",
			in:   "```json\n{\"ok\": true}\n```\n",
			want: codeFencePlain("json", []string{"{\"ok\": true}"}, width),
		},
		{
			name: "unordered list",
			in:   "- one\n- two\n\n",
			want: "· one\n· two\n",
		},
		{
			name: "ordered list",
			in:   "3. one\n4. two\n\n",
			want: "3. one\n4. two\n",
		},
		{
			name: "blockquote",
			in:   "> quoted\n> more\n\n",
			want: "  quoted\n  more\n",
		},
		{
			name: "thematic break",
			in:   "---\n",
			want: strings.Repeat("-", width-2) + "\n",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := renderMarkdown(&tm, tt.in, width)
			assertANSISnapshot(t, got, tt.want)
		})
	}
}

func TestRendererWrappingWidths(t *testing.T) {
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	doc := "ascii words wrap without overflow and unicode stays counted: 世界世界 😀😀 e\u0301e\u0301\n"
	for _, width := range []int{60, 80, 120, 200} {
		r := NewRenderer(&tm, NewHighlighter(&tm), width)
		r.Feed(tokenize(doc))
		for _, seg := range r.segments {
			if seg.Width > width-2 {
				t.Fatalf("width %d segment overflow: %d > %d in %q", width, seg.Width, width-2, seg.Plain)
			}
		}
	}
}

func TestRendererResizeRewraps(t *testing.T) {
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	doc := "one two three four five six seven eight nine ten\n"
	r := NewRenderer(&tm, NewHighlighter(&tm), 80)
	r.Feed(tokenize(doc))
	wide := stripANSI(r.Full())
	r.Resize(14)
	narrow := stripANSI(r.Full())
	if wide == narrow {
		t.Fatalf("resize did not rewrap")
	}
	for _, seg := range r.segments {
		if seg.Width > 12 {
			t.Fatalf("resized segment overflow: %d", seg.Width)
		}
	}
}

func TestRendererCodeDeltaReplacesPendingLine(t *testing.T) {
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	r := NewRenderer(&tm, NewHighlighter(&tm), 40)
	r.Feed([]Event{
		BlockOpenEvent{Kind: BlockCodeFence, Info: "go"},
		CodeBlockDeltaEvent{Lang: "go", Line: "fmt.", Final: false},
	})
	r.Feed([]Event{CodeBlockDeltaEvent{Lang: "go", Line: "fmt.Println(1)", Final: true}, BlockCloseEvent{Kind: BlockCodeFence}, CommitEvent{}})
	got := stripANSI(r.Full())
	if strings.Contains(got, "fmt.\n  fmt.Println") {
		t.Fatalf("pending code line was appended, not replaced:\n%q", got)
	}
	if !strings.Contains(got, "  fmt.Println(1)\n") {
		t.Fatalf("final code line missing:\n%q", got)
	}
}

func renderMarkdown(tm *theme.Theme, doc string, width int) string {
	s := NewStreamer(tm, NewHighlighter(tm), width)
	s.Write([]byte(doc))
	s.Close()
	return s.Full()
}

func codeFencePlain(lang string, lines []string, width int) string {
	var b strings.Builder
	for _, line := range lines {
		b.WriteString("  ")
		b.WriteString(line)
		b.WriteByte('\n')
	}
	return b.String()
}

func assertANSISnapshot(t *testing.T, got, wantPlain string) {
	t.Helper()
	if !ansiComplete(got) {
		t.Fatalf("incomplete ANSI sequence in %q", got)
	}
	if plain := stripANSI(got); plain != wantPlain {
		t.Fatalf("plain snapshot mismatch\nwant:\n%q\n got:\n%q", wantPlain, plain)
	}
}

func ansiComplete(s string) bool {
	for i := 0; i < len(s); i++ {
		if s[i] != 0x1b {
			continue
		}
		i++
		if i >= len(s) || s[i] != '[' {
			return false
		}
		for {
			i++
			if i >= len(s) {
				return false
			}
			if s[i] >= '@' && s[i] <= '~' {
				break
			}
		}
	}
	return true
}
