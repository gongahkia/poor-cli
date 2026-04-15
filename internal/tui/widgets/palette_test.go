package widgets

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets/commands"
)

func TestPaletteFiltersSlashC(t *testing.T) {
	p := testPalette()
	p.Update(keyRunes("c"))

	got := commandIDs(p.Commands())
	want := []string{"/compact", "/clear", "/cost"}
	if !samePrefix(got, want) {
		t.Fatalf("filter mismatch: got %v want prefix %v", got, want)
	}
}

func TestPaletteSelectionEnterEmitsSelectCommandMsg(t *testing.T) {
	p := testPalette()
	p.Update(keyRunes("c"))
	p.Update(keyMsg(tea.KeyDown, "down"))
	cmd := p.Update(keyMsg(tea.KeyEnter, "enter"))
	if cmd == nil {
		t.Fatalf("enter returned nil cmd")
	}
	msg, ok := cmd().(SelectCommandMsg)
	if !ok {
		t.Fatalf("wrong msg: %#v", cmd())
	}
	if msg.CommandID != "/clear" || msg.Args != "" {
		t.Fatalf("wrong selection: %#v", msg)
	}
	if p.Open() {
		t.Fatalf("palette still open")
	}
}

func TestPaletteEscapeClosesWithResidualSlash(t *testing.T) {
	p := testPalette()
	cmd := p.Update(keyMsg(tea.KeyEsc, "esc"))
	if cmd == nil {
		t.Fatalf("esc returned nil cmd")
	}
	msg, ok := cmd().(ClosePaletteMsg)
	if !ok {
		t.Fatalf("wrong msg: %#v", cmd())
	}
	if msg.Residual != "/" {
		t.Fatalf("wrong residual: %q", msg.Residual)
	}
	if p.Open() {
		t.Fatalf("palette still open")
	}
}

func TestPaletteIncludesCustomCommandsAfterSetCustoms(t *testing.T) {
	registry := commands.NewRegistry()
	registry.SetCustoms([]commands.Command{{ID: "/deploy", Label: "/deploy", Description: "Deploy service"}})
	p := NewPalette(theme.DarkWithCapability(theme.CapabilityMonochrome), registry)
	p.Update(keyRunes("dep"))

	got := commandIDs(p.Commands())
	if len(got) != 1 || got[0] != "/deploy" {
		t.Fatalf("custom command missing: %v", got)
	}
}

func TestPaletteRendersCommandIcons(t *testing.T) {
	p := testPalette()
	view := p.View()
	if !strings.Contains(view, "› ◌ /compact") || !strings.Contains(view, "  ✗ /clear") {
		t.Fatalf("icons missing from palette view: %q", view)
	}
}

func testPalette() *Palette {
	return NewPalette(theme.DarkWithCapability(theme.CapabilityMonochrome), commands.NewRegistry())
}

func keyRunes(s string) tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(s)}
}

func keyMsg(t tea.KeyType, s string) tea.KeyMsg {
	return tea.KeyMsg{Type: t, Runes: []rune(s)}
}

func commandIDs(cmds []commands.Command) []string {
	out := make([]string, len(cmds))
	for i, cmd := range cmds {
		out[i] = cmd.ID
	}
	return out
}

func samePrefix(got, want []string) bool {
	if len(got) < len(want) {
		return false
	}
	for i := range want {
		if got[i] != want[i] {
			return false
		}
	}
	return true
}
