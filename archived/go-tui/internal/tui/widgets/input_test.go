package widgets

import (
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/config"
)

func TestInputTypingNewlineBackspace(t *testing.T) {
	i := testInput(t, "")
	send(t, i, runes("h"))
	send(t, i, runes("i"))
	send(t, i, tea.KeyMsg{Type: tea.KeyEnter})
	send(t, i, runes("中"))
	send(t, i, tea.KeyMsg{Type: tea.KeyBackspace})
	if got := i.Value(); got != "hi\n" {
		t.Fatalf("value=%q", got)
	}
	if view := i.View(8); !strings.Contains(view, "hi") {
		t.Fatalf("view missing text: %q", view)
	}
}

func TestInputCtrlEnterSubmit(t *testing.T) {
	path := filepath.Join(t.TempDir(), "history.json")
	i := testInput(t, path)
	send(t, i, runes("ship"))
	msg := send(t, i, tea.KeyMsg{Type: tea.KeyCtrlJ})
	submit, ok := msg.(SubmitMsg)
	if !ok {
		t.Fatalf("msg=%T", msg)
	}
	if submit.Text != "ship" || i.Value() != "" {
		t.Fatalf("submit=%q value=%q", submit.Text, i.Value())
	}
	if got := i.history.Entries(); len(got) != 1 || got[0] != "ship" {
		t.Fatalf("history=%#v", got)
	}
	reloaded := NewHistory(path, 500)
	if got := reloaded.Entries(); len(got) != 1 || got[0] != "ship" {
		t.Fatalf("persisted=%#v", got)
	}
}

func TestInputCtrlCCancel(t *testing.T) {
	i := testInput(t, "")
	msg := send(t, i, tea.KeyMsg{Type: tea.KeyCtrlC})
	if _, ok := msg.(CancelMsg); !ok {
		t.Fatalf("msg=%T", msg)
	}
}

func TestInputPastePreservesNewlines(t *testing.T) {
	i := testInput(t, "")
	msg := send(t, i, tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("a\nb\nc"), Paste: true})
	if msg != nil {
		t.Fatalf("paste emitted %T", msg)
	}
	if got := i.Value(); got != "a\nb\nc" {
		t.Fatalf("value=%q", got)
	}
}

func TestInputHistoryUpDown(t *testing.T) {
	h := NewHistory("", 500)
	h.Push("one")
	h.Push("two")
	i := NewInputField(InputDeps{Keymap: testKeymap(t), History: h})
	send(t, i, tea.KeyMsg{Type: tea.KeyUp})
	if got := i.Value(); got != "two" {
		t.Fatalf("up=%q", got)
	}
	send(t, i, tea.KeyMsg{Type: tea.KeyUp})
	if got := i.Value(); got != "one" {
		t.Fatalf("second up=%q", got)
	}
	send(t, i, tea.KeyMsg{Type: tea.KeyDown})
	if got := i.Value(); got != "two" {
		t.Fatalf("down=%q", got)
	}
	send(t, i, tea.KeyMsg{Type: tea.KeyDown})
	if got := i.Value(); got != "" {
		t.Fatalf("uncycle=%q", got)
	}
}

func TestInputSlashAndMentionTriggers(t *testing.T) {
	i := testInput(t, "")
	msg := send(t, i, runes("/"))
	if _, ok := msg.(PaletteOpenMsg); !ok {
		t.Fatalf("slash msg=%T", msg)
	}
	if got := i.Value(); got != "" {
		t.Fatalf("slash leaked=%q", got)
	}
	msg = send(t, i, runes("@"))
	mention, ok := msg.(MentionOpenMsg)
	if !ok {
		t.Fatalf("mention msg=%T", msg)
	}
	if mention.Prefix != "" || mention.CursorPos != 1 {
		t.Fatalf("mention=%#v", mention)
	}
	msg = send(t, i, runes("ab"))
	mention, ok = msg.(MentionOpenMsg)
	if !ok || mention.Prefix != "ab" || mention.CursorPos != 3 {
		t.Fatalf("mention update=%#v %T", mention, msg)
	}
}

func TestInputUnicodeCursorClusters(t *testing.T) {
	i := testInput(t, "")
	send(t, i, runes("中"))
	send(t, i, runes("👨‍👩‍👧‍👦"))
	if got := i.CursorPos(); got != 2 {
		t.Fatalf("cursor=%d", got)
	}
	send(t, i, tea.KeyMsg{Type: tea.KeyLeft})
	i.InsertAt("界")
	if got := i.Value(); got != "中界👨‍👩‍👧‍👦" {
		t.Fatalf("value=%q", got)
	}
}

func testInput(t *testing.T, historyPath string) *InputField {
	t.Helper()
	return NewInputField(InputDeps{Keymap: testKeymap(t), History: NewHistory(historyPath, 500)})
}

func testKeymap(t *testing.T) *config.Keymap {
	t.Helper()
	km, err := config.NewKeymap(config.DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	return km
}

func runes(s string) tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(s)}
}

func send(t *testing.T, i *InputField, msg tea.KeyMsg) tea.Msg {
	t.Helper()
	_, cmd := i.Update(msg)
	if cmd == nil {
		return nil
	}
	return cmd()
}
