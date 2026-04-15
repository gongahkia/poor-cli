package markdown

import (
	"bytes"
	"testing"

	"github.com/gongahkia/gocli-poor/internal/theme"
)

func FuzzStreamer_ByteSplit(f *testing.F) {
	f.Add([]byte("# hello\n\nworld\n"), []byte{1, 2, 3})
	f.Add([]byte("```go\nfmt.Println(1)\n```\n"), []byte{4, 1})
	f.Add([]byte("- one\n- two\n> quote\n"), []byte{0, 7, 2})
	f.Fuzz(func(t *testing.T, doc []byte, splitSeeds []byte) {
		if len(doc) > 16*1024 {
			doc = doc[:16*1024]
		}
		tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
		full := NewStreamer(&tm, NewHighlighter(&tm), 72)
		full.Write(doc)
		full.Close()

		streamed := NewStreamerWithDeps(RendererDeps{Theme: &tm, Highlighter: NewHighlighter(&tm), Width: 72})
		if len(splitSeeds) == 0 {
			splitSeeds = []byte{1}
		}
		for off, i := 0, 0; off < len(doc); i++ {
			step := int(splitSeeds[i%len(splitSeeds)]%17) + 1
			end := off + step
			if end > len(doc) {
				end = len(doc)
			}
			streamed.Write(doc[off:end])
			_, _ = streamed.Drain()
			off = end
		}
		streamed.Resize(72)
		streamed.Close()
		if !bytes.Equal([]byte(streamed.Full()), []byte(full.Full())) {
			t.Fatalf("split render mismatch")
		}
	})
}
