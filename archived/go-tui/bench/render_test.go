package bench

import (
	"fmt"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/markdown"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
)

const (
	benchWidth       = 80
	benchHeight      = 24
	targetFrame      = time.Second / 60
	streamTokenRate  = 200
	streamTokenCount = 200
)

func BenchmarkMarkdownStreamer_Chunk(b *testing.B) {
	doc := benchMarkdown(256 * 1024)
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	chunks := chunkBytes([]byte(doc), 256)
	b.SetBytes(int64(len(doc)))
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		s := markdown.NewStreamer(&tm, markdown.NewHighlighter(&tm), benchWidth)
		for _, chunk := range chunks {
			s.Write(chunk)
			_, _ = s.Drain()
		}
		_ = s.Close()
	}
}

func BenchmarkChatView_AppendChunk(b *testing.B) {
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	renderer := markdown.NewRenderer(&tm, markdown.NewHighlighter(&tm), benchWidth)
	chunks := benchTokenChunks(512)
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		c := widgets.NewChat(&tm, renderer)
		s := markdown.NewStreamer(&tm, markdown.NewHighlighter(&tm), benchWidth)
		var mark markdown.Mark
		c.SetMessages([]state.Message{{ID: "a1", Role: state.RoleAssistant, RequestID: "r1", Streaming: true}})
		_ = c.View(benchWidth, benchHeight)
		for _, chunk := range chunks {
			s.Write([]byte(chunk))
			_, _ = s.Drain()
			tail, next := s.TailSince(mark)
			mark = next
			c.AppendChunk("r1", chunk, segmentsFromTail(tail))
			_ = c.View(benchWidth, benchHeight)
		}
	}
}

func BenchmarkRenderer_TailSince(b *testing.B) {
	doc := benchMarkdown(256 * 1024)
	tm := theme.DarkWithCapability(theme.CapabilityTrueColor)
	s := markdown.NewStreamer(&tm, markdown.NewHighlighter(&tm), benchWidth)
	marks := make([]markdown.Mark, 0, 4096)
	var mark markdown.Mark
	for _, chunk := range chunkBytes([]byte(doc), 256) {
		s.Write(chunk)
		if events, _ := s.Drain(); len(events) > 0 {
			_, mark = s.TailSince(mark)
			marks = append(marks, mark)
		}
	}
	_ = s.Close()
	if len(marks) == 0 {
		b.Fatal("no renderer marks")
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := range b.N {
		prev := markdown.Mark(0)
		if i > 0 {
			prev = marks[(i-1)%len(marks)]
		}
		tail, next := s.TailSince(prev)
		if next < prev || len(tail) == 0 {
			b.Fatalf("bad tail: prev=%d next=%d len=%d", prev, next, len(tail))
		}
	}
}

func benchMarkdown(minBytes int) string {
	unit := strings.Join([]string{
		"# Streaming renderer",
		"",
		"Streaming markdown text arrives as ordinary assistant prose with enough words to wrap across several terminal rows.",
		"",
		"Another paragraph keeps the renderer busy without switching language modes or blocking on terminal I/O.",
		"",
		"Short status updates continue the stream while preserving normal markdown paragraph boundaries.",
		"",
	}, "\n")
	var b strings.Builder
	for b.Len() < minBytes {
		b.WriteString(unit)
	}
	return b.String()
}

func benchTokenChunks(n int) []string {
	chunks := make([]string, n)
	for i := range chunks {
		chunks[i] = fmt.Sprintf("token-%03d ", i)
		if i%16 == 15 {
			chunks[i] += "\n\n"
		}
	}
	return chunks
}

func chunkBytes(in []byte, size int) [][]byte {
	out := make([][]byte, 0, (len(in)+size-1)/size)
	for len(in) > 0 {
		n := size
		if len(in) < n {
			n = len(in)
		}
		out = append(out, in[:n])
		in = in[n:]
	}
	return out
}

func segmentsFromTail(tail string) []markdown.Segment {
	tail = strings.TrimSuffix(tail, "\n")
	if tail == "" {
		return nil
	}
	lines := strings.Split(tail, "\n")
	segs := make([]markdown.Segment, 0, len(lines))
	for _, line := range lines {
		segs = append(segs, markdown.Segment{Text: line, Plain: line, Width: len(line)})
	}
	return segs
}

func resourceSnapshot() (time.Duration, uint64) {
	var ru syscall.Rusage
	_ = syscall.Getrusage(syscall.RUSAGE_SELF, &ru)
	cpu := time.Duration(ru.Utime.Sec+ru.Stime.Sec)*time.Second + time.Duration(ru.Utime.Usec+ru.Stime.Usec)*time.Microsecond
	rss := uint64(ru.Maxrss)
	if runtime.GOOS != "darwin" {
		rss *= 1024
	}
	return cpu, rss
}
