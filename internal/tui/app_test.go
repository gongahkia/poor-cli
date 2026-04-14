package tui

import (
	"bytes"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/exp/teatest"
)

func TestResizePreservesChatScrollAnchor(t *testing.T) {
	m := NewModel(nil)
	m.ChatScrollAnchor = 42
	tm := teatest.NewTestModel(t, m, teatest.WithInitialTermSize(80, 24))
	t.Cleanup(func() { _ = tm.Quit() })

	tm.Send(ResizeMsg{Width: 100, Height: 30})
	tm.Send(ToastMsg{Kind: ToastInfo, Text: "resized", TTL: time.Second})
	waitForText(t, tm, "resized")

	final := finalModel(t, tm)
	if final.ChatScrollAnchor != 42 {
		t.Fatalf("scroll anchor changed: got %d", final.ChatScrollAnchor)
	}
	if final.Regions.Input.Width != 100 {
		t.Fatalf("input width not recomputed: got %d", final.Regions.Input.Width)
	}
}

func TestSlashAtEmptyInputOpensPalette(t *testing.T) {
	tm := teatest.NewTestModel(t, NewModel(nil), teatest.WithInitialTermSize(80, 24))
	t.Cleanup(func() { _ = tm.Quit() })

	tm.Send(IntroDoneMsg{})
	tm.Type("/")
	waitForText(t, tm, "command palette")

	final := finalModel(t, tm)
	if final.Modals.Len() != 1 {
		t.Fatalf("palette modal not opened")
	}
	top, ok := final.Modals.Top()
	if !ok || top.Kind != ModalPalette {
		t.Fatalf("wrong modal: %#v", top)
	}
	if final.Input != "" {
		t.Fatalf("slash leaked into input: %q", final.Input)
	}
}

func TestEscapeClosesOpenModal(t *testing.T) {
	tm := teatest.NewTestModel(t, NewModel(nil), teatest.WithInitialTermSize(80, 24))
	t.Cleanup(func() { _ = tm.Quit() })

	tm.Send(OpenModalMsg{Kind: ModalProviderPicker})
	tm.Send(tea.KeyMsg{Type: tea.KeyEsc})
	tm.Send(ToastMsg{Kind: ToastInfo, Text: "closed", TTL: time.Second})
	waitForText(t, tm, "closed")

	final := finalModel(t, tm)
	if final.Modals.Len() != 0 {
		t.Fatalf("modal still open: %d", final.Modals.Len())
	}
	if final.Focus.Target != FocusInput {
		t.Fatalf("focus not restored: %v", final.Focus.Target)
	}
}

func TestTypingWithModalOpenGoesToModal(t *testing.T) {
	tm := teatest.NewTestModel(t, NewModel(nil), teatest.WithInitialTermSize(80, 24))
	t.Cleanup(func() { _ = tm.Quit() })

	tm.Send(OpenModalMsg{Kind: ModalMention})
	tm.Type("abc")
	waitForText(t, tm, "abc")

	final := finalModel(t, tm)
	if final.Input != "" {
		t.Fatalf("input changed while modal open: %q", final.Input)
	}
	top, ok := final.Modals.Top()
	if !ok {
		t.Fatalf("modal closed unexpectedly")
	}
	if top.Input != "abc" {
		t.Fatalf("modal did not receive input: %q", top.Input)
	}
}

func waitForText(t *testing.T, tm *teatest.TestModel, text string) {
	t.Helper()
	teatest.WaitFor(t, tm.Output(), func(out []byte) bool {
		return bytes.Contains(out, []byte(text))
	}, teatest.WithDuration(time.Second), teatest.WithCheckInterval(10*time.Millisecond))
}

func finalModel(t *testing.T, tm *teatest.TestModel) Model {
	t.Helper()
	if err := tm.Quit(); err != nil {
		t.Fatal(err)
	}
	fm := tm.FinalModel(t, teatest.WithFinalTimeout(time.Second))
	final, ok := fm.(Model)
	if !ok {
		t.Fatalf("wrong model type: %T", fm)
	}
	return final
}
