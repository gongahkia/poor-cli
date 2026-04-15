package flows

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
)

func TestAPIKeyPromptUpdateViewAndError(t *testing.T) {
	rpc := &fakeRPC{handlers: map[string]func(any, any) error{
		protocol.MethodSetAPIKey: func(params any, result any) error {
			p := params.(protocol.SetApiKeyParams)
			if p.Provider != "openai" || p.APIKey != "sk" || p.Persist == nil || *p.Persist {
				t.Fatalf("params=%#v", p)
			}
			return setResult(result, protocol.SetAPIKeyResult{Success: true, Provider: "openai"})
		},
	}}
	prompt := NewAPIKeyPrompt("openai", "missing")
	prompt.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("sky")}, rpc)
	prompt.Update(tea.KeyMsg{Type: tea.KeyBackspace}, rpc)
	prompt.Update(tea.KeyMsg{Type: tea.KeySpace}, rpc)
	if prompt.Input != "sk" || prompt.Persist {
		t.Fatalf("prompt=%#v", prompt)
	}
	msg := prompt.Update(tea.KeyMsg{Type: tea.KeyEnter}, rpc)().(APIKeySubmittedMsg)
	if msg.Err != nil || !msg.Result.Success {
		t.Fatalf("msg=%#v", msg)
	}
	prompt.SetError(errors.New("bad"))
	if !strings.Contains(prompt.View(40, 10), "error: bad") {
		t.Fatalf("view=%q", prompt.View(40, 10))
	}
	prompt.Clear()
	if prompt.Input != "" {
		t.Fatalf("clear failed")
	}
}

func TestProviderAndSessionPickerViewsAndCommands(t *testing.T) {
	rpc := &fakeRPC{handlers: map[string]func(any, any) error{
		protocol.MethodSwitchProvider: func(_ any, result any) error {
			return setResult(result, protocol.SwitchProviderResult{Success: true, Provider: protocol.ProviderInfo{Name: "ollama", Model: "m2"}})
		},
		protocol.MethodSwitchSession: func(_ any, result any) error {
			return setResult(result, protocol.SwitchSessionResult{Session: protocol.SessionSummary{SessionID: "s1"}})
		},
		protocol.MethodListCheckpoints: func(_ any, result any) error {
			return setResult(result, protocol.ListCheckpointsResult{Available: true})
		},
		protocol.MethodRestoreSession: func(_ any, result any) error {
			return setResult(result, RestoreSessionResult{Session: protocol.SessionSummary{SessionID: "s1"}})
		},
	}}
	pp := NewProviderPicker("ollama", "m2")
	pp.ApplyLoaded(ProvidersLoadedMsg{Result: protocol.ListProvidersResult{
		"bad":    {Available: false, Ready: false, Models: []string{"x"}},
		"ollama": {Available: true, Ready: true, Models: []string{"m1", "m2"}},
		"openai": {Available: true, Ready: false, Models: []string{"gpt"}},
	}})
	pp.Update(tea.KeyMsg{Type: tea.KeyRight})
	pp.Update(tea.KeyMsg{Type: tea.KeyLeft})
	if !strings.Contains(pp.View(80, 8), "ollama") {
		t.Fatalf("provider view=%q", pp.View(80, 8))
	}
	if msg := SwitchProviderCmd(rpc, ProviderChoice{Provider: "ollama", Model: "m2"}, protocol.ProviderInfo{})().(ProviderSwitchedMsg); msg.Err != nil || msg.Result.Provider.Model != "m2" {
		t.Fatalf("provider switch=%#v", msg)
	}

	sp := NewSessionPicker("")
	sp.ApplyLoaded(SessionsLoadedMsg{Result: protocol.ListSessionsResult{
		ActiveSessionID: "s1",
		Sessions:        []protocol.SessionSummary{{ID: "fallback", UpdatedAt: 1}, {SessionID: "s1", Label: "main", Model: "m", UpdatedAt: 2}},
	}})
	sp.Update(tea.KeyMsg{Type: tea.KeyDown})
	sp.Update(tea.KeyMsg{Type: tea.KeyUp})
	if !strings.Contains(sp.View(80, 8), "main") {
		t.Fatalf("session view=%q", sp.View(80, 8))
	}
	if msg := SwitchSessionCmd(rpc, protocol.SessionSummary{SessionID: "s1"})().(SessionSwitchedMsg); msg.Err != nil || msg.Result.Session.SessionID != "s1" {
		t.Fatalf("session switch=%#v", msg)
	}
	if msg := FetchCheckpointsCmd(rpc, "s1")().(CheckpointsLoadedMsg); msg.Err != nil || !msg.Result.Available {
		t.Fatalf("checkpoints=%#v", msg)
	}
	if msg := RestoreSessionCmd(rpc, "s1", "cp1")().(SessionRestoredMsg); msg.Err != nil || msg.Result.Session.SessionID != "s1" {
		t.Fatalf("restore=%#v", msg)
	}
}

func TestRegistryLifecycleAndHudStartStop(t *testing.T) {
	reg := NewRegistry()
	lf := &lifecycleFlow{}
	reg.Register(lf)
	if err := reg.StartAll(context.Background(), Deps{}); err != nil {
		t.Fatal(err)
	}
	if !lf.started {
		t.Fatal("not started")
	}
	if cmds := reg.UpdateAll(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("x")}); len(cmds) != 1 || cmds[0]() == nil {
		t.Fatalf("cmds=%#v", cmds)
	}
	if err := reg.StopAll(); err != nil || !lf.stopped {
		t.Fatalf("stop err=%v stopped=%v", err, lf.stopped)
	}

	store := state.NewStore()
	defer store.Close()
	rpc := &mockNotifyRPC{fakeRPC: fakeRPC{handlers: map[string]func(any, any) error{
		protocol.MethodGetContextPressure: func(_ any, result any) error {
			return setResult(result, protocol.ContextPressure{UsedTokens: 2, MaxTokens: 10, PressurePct: 20})
		},
	}}}
	hud := NewHudFlow(Deps{RPC: rpc, Store: store})
	ctx, cancel := context.WithCancel(context.Background())
	if err := hud.StartFlow(ctx, Deps{}); err != nil {
		t.Fatal(err)
	}
	rpc.emit(protocol.MethodCostUpdate, protocol.CostUpdate{InputTokens: 1, OutputTokens: 2, EstimatedCost: 0.01})
	time.Sleep(150 * time.Millisecond)
	cancel()
	if err := hud.Stop(); err != nil {
		t.Fatal(err)
	}
	if store.Snapshot().Cost.InputTokens != 1 {
		t.Fatalf("cost=%#v", store.Snapshot().Cost)
	}
}

type lifecycleFlow struct {
	started bool
	stopped bool
}

func (l *lifecycleFlow) Name() string { return "life" }
func (l *lifecycleFlow) Stop() error  { l.stopped = true; return nil }
func (l *lifecycleFlow) Update(tea.Msg) tea.Cmd {
	return func() tea.Msg { return hudTickMsg{} }
}
func (l *lifecycleFlow) StartFlow(context.Context, Deps) error {
	l.started = true
	return nil
}

type mockNotifyRPC struct {
	fakeRPC
	subs map[string][]NotificationHandler
}

func (m *mockNotifyRPC) Subscribe(method string, h NotificationHandler) func() {
	if m.subs == nil {
		m.subs = map[string][]NotificationHandler{}
	}
	m.subs[method] = append(m.subs[method], h)
	return func() {}
}

func (m *mockNotifyRPC) emit(method string, params any) {
	for _, h := range m.subs[method] {
		h(params)
	}
}
