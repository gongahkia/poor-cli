package markdown

import (
	"strconv"
	"testing"

	"github.com/gongahkia/gocli-poor/internal/theme"
)

func TestHighlighterGoldenLines(t *testing.T) {
	th := theme.DarkWithCapability(theme.CapabilityTrueColor)
	hl := NewHighlighter(&th)
	tests := []struct {
		name string
		lang string
		line string
		want string
	}{
		{"go", "go", `fmt.Println("hello")`, "\x1b[38;2;243;243;245mfmt\x1b[0m\x1b[38;2;243;243;245m.\x1b[0m\x1b[38;2;137;179;250mPrintln\x1b[0m\x1b[38;2;243;243;245m(\x1b[0m\x1b[38;2;166;227;161m\"hello\"\x1b[0m\x1b[38;2;243;243;245m)\x1b[0m"},
		{"python", "python", `def hello(): print("hi")`, "\x1b[38;2;137;179;250mdef\x1b[0m\x1b[38;2;243;243;245m \x1b[0m\x1b[38;2;137;179;250mhello\x1b[0m\x1b[38;2;243;243;245m():\x1b[0m\x1b[38;2;243;243;245m \x1b[0m\x1b[38;2;243;243;245mprint\x1b[0m\x1b[38;2;243;243;245m(\x1b[0m\x1b[38;2;166;227;161m\"hi\"\x1b[0m\x1b[38;2;243;243;245m)\x1b[0m"},
		{"json", "json", `{"a": 1}`, "\x1b[38;2;243;243;245m{\x1b[0m\x1b[38;2;243;243;245m\"a\"\x1b[0m\x1b[38;2;243;243;245m:\x1b[0m\x1b[38;2;243;243;245m \x1b[0m\x1b[38;2;249;226;175m1\x1b[0m\x1b[38;2;243;243;245m}\x1b[0m"},
		{"bash", "bash", `ls -la | grep foo`, "\x1b[38;2;243;243;245mls -la \x1b[0m\x1b[38;2;243;243;245m|\x1b[0m\x1b[38;2;243;243;245m grep foo\x1b[0m"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := hl.HighlightLine(tt.lang, tt.line)
			if got != tt.want {
				t.Fatalf("golden mismatch\nwant: %s\n got: %s", strconv.Quote(tt.want), strconv.Quote(got))
			}
		})
	}
}

func TestHighlighterUnknownLangPassthrough(t *testing.T) {
	th := theme.DarkWithCapability(theme.CapabilityTrueColor)
	hl := NewHighlighter(&th)
	const line = `fmt.Println("plain")`
	if got := hl.HighlightLine("does-not-exist", line); got != line {
		t.Fatalf("got %q want passthrough", got)
	}
}

func TestHighlighterBlockAndAlias(t *testing.T) {
	th := theme.DarkWithCapability(theme.CapabilityTrueColor)
	hl := NewHighlighter(&th)
	got := hl.HighlightBlock("golang", "package main\n")
	if got == "package main\n" {
		t.Fatal("alias was not highlighted")
	}
}

func TestHighlighterCachesLexerResolution(t *testing.T) {
	th := theme.DarkWithCapability(theme.CapabilityTrueColor)
	hl := NewHighlighter(&th)
	hl.HighlightLine("go", "package main")
	first := hl.lexers["go"]
	hl.HighlightLine("go", "func main() {}")
	if second := hl.lexers["go"]; first != second {
		t.Fatal("lexer cache miss on warm lookup")
	}
	if got := len(hl.lexers); got != 1 {
		t.Fatalf("cache size = %d, want 1", got)
	}
}
