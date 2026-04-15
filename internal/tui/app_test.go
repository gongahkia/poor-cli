package tui

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/exp/teatest"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/tui/flows"
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

func TestPaletteInputRunsSlashCommandWithoutLeadingSlash(t *testing.T) {
	rpc := &appRPC{handlers: map[string]func(any, any) error{
		protocol.MethodListProviders: func(_ any, result any) error {
			return setAppResult(result, protocol.ListProvidersResult{})
		},
	}}
	m := NewModel(nil, WithRPCClient(rpc))
	m.openModal(ModalPalette, nil)
	m.Modals.UpdateTopInput("provider")
	next, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = next.(Model)
	if cmd == nil {
		t.Fatal("missing command")
	}
	_ = cmd()
	if len(rpc.calls) != 1 || rpc.calls[0].Method != protocol.MethodListProviders {
		t.Fatalf("calls=%#v", rpc.calls)
	}
	if m.Modals.Len() == 0 {
		t.Fatal("provider modal not opened")
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

func TestProviderPickerSelectUpdatesState(t *testing.T) {
	rpc := &appRPC{handlers: map[string]func(any, any) error{
		protocol.MethodSwitchProvider: func(_ any, result any) error {
			return setAppResult(result, protocol.SwitchProviderResult{Success: true, Provider: protocol.ProviderInfo{Name: "openai", Model: "gpt-5"}})
		},
	}}
	st := &state.AppState{Provider: state.ProviderState{Name: "anthropic", Model: "old"}}
	m := NewModel(st, WithRPCClient(rpc))
	choice := flows.ProviderChoice{Provider: "openai", Model: "gpt-5", Detail: protocol.ProviderDetail{Ready: true}}
	next, cmd := m.Update(flows.ProviderSelectedMsg{Choice: choice})
	if cmd == nil {
		t.Fatalf("missing switch cmd")
	}
	m = next.(Model)
	if m.State.Provider.Name != "openai" {
		t.Fatalf("optimistic provider=%q", m.State.Provider.Name)
	}
	next, _ = m.Update(cmd())
	m = next.(Model)
	if m.State.Provider.Name != "openai" || m.State.Provider.Model != "gpt-5" {
		t.Fatalf("provider=%#v", m.State.Provider)
	}
}

func TestAPIKeyRejectKeepsModalOpenWithError(t *testing.T) {
	rpc := &appRPC{handlers: map[string]func(any, any) error{
		protocol.MethodSetAPIKey: func(_ any, _ any) error { return errors.New("bad key") },
	}}
	m := NewModel(nil, WithRPCClient(rpc))
	m.openModal(ModalAPIKeyPrompt, flows.NewAPIKeyPrompt("openai", ""))
	next, _ := m.Update(flows.APIKeySubmittedMsg{Provider: "openai", Err: errors.New("bad key")})
	m = next.(Model)
	if m.Modals.Len() != 1 {
		t.Fatalf("modal closed")
	}
	top, _ := m.Modals.Top()
	got := top.Payload.(*flows.APIKeyPrompt)
	if got.Error != "bad key" {
		t.Fatalf("error=%q", got.Error)
	}
}

func TestCostSlashOpensModalAndRendersDashboard(t *testing.T) {
	rpc := &appRPC{handlers: map[string]func(any, any) error{
		protocol.MethodCostSummary: func(_ any, result any) error {
			return setAppResult(result, protocol.CostSnapshot{
				Session:     protocol.CostSession{TotalUSD: 0.0472},
				LastTurn:    map[string]any{"cost_usd": 0.0083},
				PerProvider: map[string]any{"anthropic": 0.0412},
			})
		},
		protocol.MethodGetEconomySavings: func(_ any, result any) error {
			return setAppResult(result, protocol.SavingsSnapshot{CostSaved: 0.0134})
		},
	}}
	m := NewModel(nil, WithRPCClient(rpc))

	cmd := m.dispatchCommandInput("/cost")
	if cmd == nil || m.Modals.Len() != 1 {
		t.Fatalf("modal/cmd missing")
	}
	next, _ := m.Update(cmd())
	m = next.(Model)
	top, _ := m.Modals.Top()
	view := top.Payload.(flows.CostPayload).View(80, 20)
	if !strings.Contains(view, "Current turn:") || !strings.Contains(view, "anthropic") {
		t.Fatalf("view=%q", view)
	}
}

type appRPC struct {
	handlers map[string]func(any, any) error
	calls    []appRPCCall
}

type appRPCCall struct {
	Method string
	Params any
}

func (a *appRPC) Call(_ context.Context, method string, params any, result any) error {
	a.calls = append(a.calls, appRPCCall{Method: method, Params: params})
	if h := a.handlers[method]; h != nil {
		return h(params, result)
	}
	return nil
}

func setAppResult(dst any, src any) error {
	b, err := json.Marshal(src)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, dst)
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
