package bench

import (
	"encoding/json"
	"fmt"
	"net"
	"sort"
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/markdown"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/transport"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
)

type streamFrame struct {
	Index int    `json:"i"`
	Token string `json:"t"`
}

func BenchmarkE2E_200TokPerSec(b *testing.B) {
	b.ReportAllocs()
	for range b.N {
		result := runStreamingE2E(b)
		b.ReportMetric(result.cpuPct, "cpu_core_pct")
		b.ReportMetric(float64(result.droppedFrames), "dropped_frames/op")
		b.ReportMetric(float64(result.frames), "frames/op")
		b.ReportMetric(float64(result.tokens)/result.wall.Seconds(), "tok/s")
		b.ReportMetric(float64(result.maxFrame.Microseconds())/1000, "max_frame_ms")
		b.ReportMetric(float64(result.p95Frame.Microseconds())/1000, "p95_frame_ms")
		b.ReportMetric(float64(result.rssBytes)/(1024*1024), "rss_mb")
	}
}

type streamResult struct {
	tokens        int
	frames        int
	droppedFrames int
	wall          time.Duration
	maxFrame      time.Duration
	p95Frame      time.Duration
	cpuPct        float64
	rssBytes      uint64
}

func runStreamingE2E(tb testing.TB) streamResult {
	server, client := net.Pipe()
	defer client.Close()
	errc := make(chan error, 1)
	go syntheticStreamServer(server, streamTokenCount, time.Second/streamTokenRate, errc)

	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	md := markdown.NewStreamer(&tm, markdown.NewHighlighter(&tm), benchWidth)
	chat := widgets.NewChat(&tm, markdown.NewRenderer(&tm, markdown.NewHighlighter(&tm), benchWidth))
	chat.SetMessages([]state.Message{{ID: "a1", Role: state.RoleAssistant, RequestID: "r1", Streaming: true}})
	reader := transport.NewReader(client)
	startCPU, _ := resourceSnapshot()
	start := time.Now()
	nextFrame := start
	latencies := make([]time.Duration, 0, 64)
	var mark markdown.Mark
	tokens := 0
	for tokens < streamTokenCount {
		body, err := reader.ReadMessage()
		if err != nil {
			tb.Fatalf("read stream: %v", err)
		}
		var frame streamFrame
		if err := json.Unmarshal(body, &frame); err != nil {
			tb.Fatalf("decode stream: %v", err)
		}
		md.Write([]byte(frame.Token))
		_, _ = md.Drain()
		tail, next := md.TailSince(mark)
		mark = next
		chat.AppendChunk("r1", frame.Token, segmentsFromTail(tail))
		tokens++
		now := time.Now()
		if !now.Before(nextFrame) {
			paintStart := time.Now()
			_ = chat.View(benchWidth, benchHeight)
			latencies = append(latencies, time.Since(paintStart))
			nextFrame = nextFrame.Add(targetFrame)
		}
	}
	_ = md.Close()
	paintStart := time.Now()
	_ = chat.View(benchWidth, benchHeight)
	latencies = append(latencies, time.Since(paintStart))
	if err := <-errc; err != nil {
		tb.Fatalf("synthetic stream: %v", err)
	}
	wall := time.Since(start)
	endCPU, rss := resourceSnapshot()
	return streamResult{
		tokens:        tokens,
		frames:        len(latencies),
		droppedFrames: countDropped(latencies),
		wall:          wall,
		maxFrame:      maxDuration(latencies),
		p95Frame:      percentileDuration(latencies, 0.95),
		cpuPct:        100 * float64(endCPU-startCPU) / float64(wall),
		rssBytes:      rss,
	}
}

func syntheticStreamServer(conn net.Conn, n int, cadence time.Duration, errc chan<- error) {
	defer conn.Close()
	writer := transport.NewWriter(conn)
	ticker := time.NewTicker(cadence)
	defer ticker.Stop()
	for i := 0; i < n; i++ {
		<-ticker.C
		body, err := json.Marshal(streamFrame{Index: i, Token: fmt.Sprintf("token-%03d\n\n", i)})
		if err != nil {
			errc <- err
			return
		}
		if err := writer.WriteMessage(body); err != nil {
			errc <- err
			return
		}
	}
	errc <- nil
}

func countDropped(latencies []time.Duration) int {
	dropped := 0
	for _, latency := range latencies {
		if latency > targetFrame {
			dropped++
		}
	}
	return dropped
}

func maxDuration(values []time.Duration) time.Duration {
	var max time.Duration
	for _, value := range values {
		if value > max {
			max = value
		}
	}
	return max
}

func percentileDuration(values []time.Duration, q float64) time.Duration {
	if len(values) == 0 {
		return 0
	}
	cp := append([]time.Duration(nil), values...)
	sort.Slice(cp, func(i, j int) bool { return cp[i] < cp[j] })
	idx := int(float64(len(cp)-1) * q)
	return cp[idx]
}
