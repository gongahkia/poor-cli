package widgets

import (
	"strings"
	"testing"
	"unicode/utf8"

	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
)

func TestStatusBarWidth120ShowsAllSlots(t *testing.T) {
	bar := testStatusBar()
	out := bar.View(120)
	for _, want := range []string{"●", "anthropic:claude-sonnet-4-20250514", "session:#abcd1234", "ctx:85%", "tok:123456/789012", "$2.50"} {
		if !strings.Contains(out, want) {
			t.Fatalf("missing %q in %q", want, out)
		}
	}
	if got := lipgloss.Width(out); got != 120 {
		t.Fatalf("width=%d", got)
	}
}

func TestStatusBarDropsRightmostOptionalSlots(t *testing.T) {
	bar := testStatusBar()
	out := bar.View(80)
	if strings.Contains(out, "tok:123456/789012") {
		t.Fatalf("tokens not dropped: %q", out)
	}
	for _, want := range []string{"session:#abcd1234", "ctx:85%", "anthropic:claude-sonnet-4-20250514", "$2.50"} {
		if !strings.Contains(out, want) {
			t.Fatalf("missing %q in %q", want, out)
		}
	}

	out = bar.View(60)
	for _, dropped := range []string{"tok:123456/789012", "ctx:85%", "session:#abcd1234"} {
		if strings.Contains(out, dropped) {
			t.Fatalf("slot %q not dropped: %q", dropped, out)
		}
	}
	for _, want := range []string{"anthropic:claude-sonnet-4-20250514", "$2.50"} {
		if !strings.Contains(out, want) {
			t.Fatalf("missing mandatory %q in %q", want, out)
		}
	}
}

func TestStatusBarTruncatesCleanly(t *testing.T) {
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	bar := &StatusBar{theme: tm, snapshot: state.AppState{
		Provider: state.ProviderState{Name: "模型", Model: "gpt-🚀-extended"},
		Cost:     state.CostState{SessionTotalUSD: 0.42},
	}}
	out := bar.View(12)
	if !utf8.ValidString(out) {
		t.Fatalf("invalid utf8: %q", out)
	}
	if got := lipgloss.Width(out); got != 12 {
		t.Fatalf("width=%d out=%q", got, out)
	}
}

func TestStatusBarCostThresholdStylesChange(t *testing.T) {
	tm := theme.DarkWithCapability(theme.CapabilityTrueColor)
	bar := &StatusBar{theme: tm}
	rendered := []string{
		bar.costStyle(0.01).Render("$x"),
		bar.costStyle(0.05).Render("$x"),
		bar.costStyle(0.25).Render("$x"),
	}
	if rendered[0] == rendered[1] || rendered[1] == rendered[2] || rendered[0] == rendered[2] {
		t.Fatalf("cost styles did not change: %#v", rendered)
	}
}

func TestStatusBarReadsStoreSubscription(t *testing.T) {
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	store := state.NewStore()
	defer store.Close()
	bar := NewStatusBar(StatusBarDeps{Store: store, Theme: &tm})
	defer bar.Close()

	store.Dispatch(state.ActionSetProvider{Info: protocol.ProviderInfo{Name: "openai", Model: "gpt-5.4"}})
	store.Dispatch(state.ActionUpdateCost{Snapshot: protocol.CostSnapshot{SessionCost: 0.25}})
	out := bar.View(40)
	for _, want := range []string{"openai:gpt-5.4", "$0.25"} {
		if !strings.Contains(out, want) {
			t.Fatalf("missing %q in %q", want, out)
		}
	}
}

func TestTypingFooterFormatsAndSkipsLocal(t *testing.T) {
	st := state.AppState{Multiplayer: state.MultiplayerState{
		Enabled:           true,
		LocalConnectionID: "c4",
		Members: []state.Member{
			{ConnectionID: "c1", DisplayName: "alice"},
			{ConnectionID: "c2", DisplayName: "bob"},
			{ConnectionID: "c3", DisplayName: "carol"},
			{ConnectionID: "c4", DisplayName: "dave"},
			{ConnectionID: "c5", DisplayName: "erin"},
		},
		Typing: map[string]bool{"c1": true, "c2": true, "c3": true, "c4": true, "c5": true},
	}}
	if got := TypingFooterText(st); got != "alice, bob, carol +1 typing" {
		t.Fatalf("footer=%q", got)
	}
	st.Multiplayer.Typing = nil
	if got := TypingFooterView(st, 40, nil); got != "" {
		t.Fatalf("empty footer rendered: %q", got)
	}
}

func testStatusBar() *StatusBar {
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	return &StatusBar{theme: tm, snapshot: state.AppState{
		Connection: state.ConnState{Phase: state.Ready},
		Provider:   state.ProviderState{Name: "anthropic", Model: "claude-sonnet-4-20250514"},
		Session:    state.SessionState{ID: "abcd1234ffff"},
		ContextPressure: state.ContextPressure{
			Pct: 0.85,
		},
		Cost: state.CostState{
			SessionTotalUSD: 2.50,
			InputTokens:     123456,
			OutputTokens:    789012,
		},
	}}
}
