package bench

import (
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/tui"
)

func BenchmarkStartup_FirstPaint(b *testing.B) {
	b.ReportAllocs()
	for range b.N {
		startCPU, _ := resourceSnapshot()
		start := time.Now()
		model := tui.NewModel(&state.AppState{Connection: state.ConnState{Phase: state.Ready}})
		next, _ := model.Update(tea.WindowSizeMsg{Width: benchWidth, Height: benchHeight})
		_ = next.View()
		firstPaint := time.Since(start)
		endCPU, rss := resourceSnapshot()
		b.ReportMetric(float64(firstPaint.Microseconds())/1000, "first_paint_ms")
		if firstPaint > 0 {
			b.ReportMetric(100*float64(endCPU-startCPU)/float64(firstPaint), "cpu_core_pct")
		}
		b.ReportMetric(float64(rss)/(1024*1024), "rss_mb")
	}
}
