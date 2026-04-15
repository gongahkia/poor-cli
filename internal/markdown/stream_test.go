package markdown

import (
	"strings"
	"testing"

	"github.com/gongahkia/gocli-poor/internal/theme"
)

func TestStreamerByteByByteFourKB(t *testing.T) {
	tm := theme.DarkWithCapability(theme.CapabilityTrueColor)
	doc := fourKBMarkdown()
	full := NewStreamer(&tm, NewHighlighter(&tm), 76)
	full.Write([]byte(doc))
	full.Close()

	stream := NewStreamer(&tm, NewHighlighter(&tm), 76)
	var prev Mark
	var painted strings.Builder
	lastPainted := 0
	for i := 0; i < len(doc); i++ {
		stream.Write([]byte{doc[i]})
		events, _ := stream.Drain()
		if len(events) == 0 {
			continue
		}
		tail, mark := stream.TailSince(prev)
		if mark < prev {
			t.Fatalf("mark regressed: %d < %d", mark, prev)
		}
		if !ansiComplete(tail) {
			t.Fatalf("split ANSI escape at byte %d tail %q", i, tail)
		}
		painted.WriteString(tail)
		if painted.Len() < lastPainted {
			t.Fatalf("paint output shrank")
		}
		lastPainted = painted.Len()
		prev = mark
	}
	stream.Close()
	events, _ := stream.Drain()
	if len(events) > 0 {
		tail, mark := stream.TailSince(prev)
		if !ansiComplete(tail) {
			t.Fatalf("split ANSI escape on close tail %q", tail)
		}
		painted.WriteString(tail)
		prev = mark
	}
	if stream.Full() != full.Full() {
		t.Fatalf("byte stream render != full render")
	}
	if painted.String() != stream.Full() {
		t.Fatalf("tail paints did not reconstruct full render")
	}
	if prev != stream.Mark() {
		t.Fatalf("mark mismatch: %d != %d", prev, stream.Mark())
	}
}

func fourKBMarkdown() string {
	unit := strings.Join([]string{
		"# Streaming renderer",
		"",
		"Paragraph with *emphasis*, **strong**, `code`, [link](https://example.com), CJK 世界, emoji 😀.",
		"",
		"> quoted line with enough content to wrap at normal terminal widths",
		"> second quote line",
		"",
		"- first item wraps with more words than a small terminal can hold cleanly",
		"- second item",
		"",
		"```go",
		"func main() {",
		"\tfmt.Println(\"hello\")",
		"}",
		"```",
		"",
		"```json",
		"{\"ok\": true, \"n\": 42}",
		"```",
		"",
		"---",
		"",
	}, "\n")
	var b strings.Builder
	for b.Len() < 4096 {
		b.WriteString(unit)
	}
	return b.String()
}
