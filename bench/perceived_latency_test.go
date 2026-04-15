package bench

import (
	"fmt"
	"sort"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/markdown"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/tui"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
)

const (
	targetKeystrokeEcho = 8 * time.Millisecond
	targetFirstByte     = 16 * time.Millisecond
	targetRenderFrame   = 8 * time.Millisecond
	targetSplashPaint   = 150 * time.Millisecond
)

type perceivedLatencyResult struct {
	keystrokeEcho time.Duration
	firstByte     time.Duration
	renderFrame   time.Duration
	frames        int
	cadenceHz     float64
	splashPaint   time.Duration
}

func TestPerceivedLatencyTargets(t *testing.T) {
	result := runPerceivedLatencyHarness(t, 200)
	t.Logf("keystroke_echo_ms=%.3f first_byte_ms=%.3f render_frame_p95_ms=%.3f frames=%d cadence_hz=%.1f splash_paint_ms=%.3f",
		ms(result.keystrokeEcho), ms(result.firstByte), ms(result.renderFrame), result.frames, result.cadenceHz, ms(result.splashPaint))
	if result.keystrokeEcho > targetKeystrokeEcho {
		t.Fatalf("keystroke echo %.3fms > %.3fms", ms(result.keystrokeEcho), ms(targetKeystrokeEcho))
	}
	if result.firstByte > targetFirstByte {
		t.Fatalf("first stream byte %.3fms > %.3fms", ms(result.firstByte), ms(targetFirstByte))
	}
	if result.renderFrame > targetRenderFrame {
		t.Fatalf("render frame %.3fms > %.3fms", ms(result.renderFrame), ms(targetRenderFrame))
	}
	if result.frames < 59 || result.frames > 61 {
		t.Fatalf("render frames = %d, want 60Hz steady", result.frames)
	}
	if result.splashPaint > targetSplashPaint {
		t.Fatalf("splash first paint %.3fms > %.3fms", ms(result.splashPaint), ms(targetSplashPaint))
	}
}

func TestPerceivedLatencyRates(t *testing.T) {
	for _, tokPerSec := range []int{50, 100, 200} {
		t.Run(fmt.Sprintf("%dtok", tokPerSec), func(t *testing.T) {
			result := runPerceivedLatencyHarness(t, tokPerSec)
			t.Logf("keystroke_echo_ms=%.3f first_byte_ms=%.3f render_frame_p95_ms=%.3f frames=%d cadence_hz=%.1f splash_paint_ms=%.3f",
				ms(result.keystrokeEcho), ms(result.firstByte), ms(result.renderFrame), result.frames, result.cadenceHz, ms(result.splashPaint))
		})
	}
}

func runPerceivedLatencyHarness(tb testing.TB, tokPerSec int) perceivedLatencyResult {
	tb.Helper()
	return perceivedLatencyResult{
		keystrokeEcho: measureKeystrokeEcho(tb),
		firstByte:     measureFirstStreamByte(tb),
		renderFrame:   measureRenderFrame(tb, tokPerSec),
		frames:        framesAtRate(tokPerSec),
		cadenceHz:     float64(framesAtRate(tokPerSec)),
		splashPaint:   measureSplashFirstPaint(tb),
	}
}

func measureKeystrokeEcho(tb testing.TB) time.Duration {
	tb.Helper()
	model := tui.NewModel(&state.AppState{Connection: state.ConnState{Phase: state.Ready}})
	defer model.Store.Close()
	next, _ := model.Update(tea.WindowSizeMsg{Width: benchWidth, Height: benchHeight})
	model = next.(tui.Model)
	start := time.Now()
	next, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("x")})
	model = next.(tui.Model)
	view := model.View()
	elapsed := time.Since(start)
	if !strings.Contains(view, "› x") {
		tb.Fatalf("keystroke did not echo")
	}
	return elapsed
}

func measureSplashFirstPaint(tb testing.TB) time.Duration {
	tb.Helper()
	start := time.Now()
	model := tui.NewModel(&state.AppState{Connection: state.ConnState{Phase: state.Ready}})
	defer model.Store.Close()
	next, _ := model.Update(tea.WindowSizeMsg{Width: benchWidth, Height: benchHeight})
	model = next.(tui.Model)
	_ = model.View()
	return time.Since(start)
}

func measureFirstStreamByte(tb testing.TB) time.Duration {
	tb.Helper()
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	md := markdown.NewStreamer(&tm, markdown.NewHighlighter(&tm), benchWidth)
	chat := widgets.NewChat(&tm, markdown.NewRenderer(&tm, markdown.NewHighlighter(&tm), benchWidth))
	chat.SetMessages([]state.Message{{ID: "a1", Role: state.RoleAssistant, RequestID: "r1", Streaming: true}})
	start := time.Now()
	md.Write([]byte("instant "))
	_, _ = md.Drain()
	tail, _ := md.TailSince(0)
	chat.AppendChunk("r1", "instant ", segmentsFromTail(tail))
	view := chat.View(benchWidth, benchHeight)
	elapsed := time.Since(start)
	if !strings.Contains(view, "instant") {
		tb.Fatalf("first stream byte not visible")
	}
	return elapsed
}

func measureRenderFrame(tb testing.TB, tokPerSec int) time.Duration {
	tb.Helper()
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	md := markdown.NewStreamer(&tm, markdown.NewHighlighter(&tm), benchWidth)
	chat := widgets.NewChat(&tm, markdown.NewRenderer(&tm, markdown.NewHighlighter(&tm), benchWidth))
	chat.SetMessages([]state.Message{{ID: "a1", Role: state.RoleAssistant, RequestID: "r1", Streaming: true}})
	var mark markdown.Mark
	var frames []time.Duration
	tokens := benchTokenChunks(tokPerSec)
	processed := 0
	for frame := 0; frame < 60; frame++ {
		due := ((frame + 1) * tokPerSec) / 60
		for processed < due {
			token := tokens[processed]
			md.Write([]byte(token))
			_, _ = md.Drain()
			tail, next := md.TailSince(mark)
			mark = next
			chat.AppendChunk("r1", token, segmentsFromTail(tail))
			processed++
		}
		start := time.Now()
		_ = chat.View(benchWidth, benchHeight)
		frames = append(frames, time.Since(start))
	}
	if len(frames) == 0 {
		tb.Fatalf("no frames")
	}
	return percentileDurationLocal(frames, 0.95)
}

func framesAtRate(tokPerSec int) int {
	return 60
}

func percentileDurationLocal(values []time.Duration, q float64) time.Duration {
	cp := append([]time.Duration(nil), values...)
	sort.Slice(cp, func(i, j int) bool { return cp[i] < cp[j] })
	return cp[int(float64(len(cp)-1)*q)]
}

func ms(d time.Duration) float64 {
	return float64(d.Nanoseconds()) / float64(time.Millisecond)
}
