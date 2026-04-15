package tui

import (
	"context"
	"strings"
	"sync"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/tui/flows"
)

type appChatRPC struct {
	mu       sync.Mutex
	handlers map[string][]flows.NotificationHandler
}

func newAppChatRPC() *appChatRPC {
	return &appChatRPC{handlers: map[string][]flows.NotificationHandler{}}
}

func (a *appChatRPC) Call(_ context.Context, method string, params any, result any) error {
	switch method {
	case protocol.MethodChatStreaming:
		p := params.(protocol.ChatStreamingParams)
		a.emit(protocol.MethodProgress, protocol.Progress{RequestID: p.RequestID, Phase: "chat", Message: "thinking"})
		a.emit(protocol.MethodStreamChunk, protocol.StreamChunk{RequestID: p.RequestID, Chunk: "hello"})
		a.emit(protocol.MethodStreamChunk, protocol.StreamChunk{RequestID: p.RequestID, Chunk: " tui"})
		a.emit(protocol.MethodStreamChunk, protocol.StreamChunk{RequestID: p.RequestID, Done: true})
		return setAppResult(result, protocol.ChatResult{Content: "hello tui", Role: "assistant"})
	case protocol.MethodGetContextPressure:
		return setAppResult(result, protocol.ContextPressure{UsedTokens: 1, MaxTokens: 10, PressurePct: 10})
	default:
		return nil
	}
}

func (a *appChatRPC) Notify(context.Context, string, any) error { return nil }

func (a *appChatRPC) Subscribe(method string, handler flows.NotificationHandler) func() {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.handlers[method] = append(a.handlers[method], handler)
	return func() {}
}

func (a *appChatRPC) emit(method string, params any) {
	a.mu.Lock()
	handlers := append([]flows.NotificationHandler(nil), a.handlers[method]...)
	a.mu.Unlock()
	for _, handler := range handlers {
		handler(params)
	}
}

func TestAppSubmitChatRendersStreamedResponse(t *testing.T) {
	rpc := newAppChatRPC()
	m := NewModel(&state.AppState{Connection: state.ConnState{Phase: state.Ready}}, WithRPCClient(rpc), WithIntroVersion("test"))
	next, _ := m.Update(IntroDoneMsg{})
	m = next.(Model)
	next, _ = m.Update(ResizeMsg{Width: 60, Height: 10})
	m = next.(Model)
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("say hi")})
	m = next.(Model)
	next, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = next.(Model)
	if cmd == nil {
		t.Fatal("missing submit cmd")
	}
	next, _ = m.Update(cmd())
	m = next.(Model)
	waitForStore(t, m.Store, func(st state.AppState) bool {
		return len(st.Messages) == 2 && strings.Contains(st.Messages[1].Content, "hello tui") && st.InFlight == nil
	})
	st := m.Store.Snapshot()
	next, _ = m.Update(stateUpdatedMsg{State: st})
	m = next.(Model)
	if view := m.View(); !strings.Contains(view, "you › say hi") || !strings.Contains(view, "poor-cli › hello tui") {
		t.Fatalf("view missing chat:\n%s", view)
	}
	m.Store.Close()
}

func TestAppSessionProviderAndCheckpointBranches(t *testing.T) {
	rpc := &appRPC{handlers: map[string]func(any, any) error{
		protocol.MethodListProviders: func(_ any, result any) error {
			return setAppResult(result, protocol.ListProvidersResult{
				"ollama": {Available: true, Ready: true, Models: []string{"llama3.1"}},
			})
		},
		protocol.MethodListSessions: func(_ any, result any) error {
			return setAppResult(result, protocol.ListSessionsResult{
				ActiveSessionID: "s2",
				Sessions: []protocol.SessionSummary{
					{SessionID: "s1", Title: "older", UpdatedAt: 1, MessageCount: 1, Model: "m1"},
					{SessionID: "s2", Label: "newer", UpdatedAt: 2, MessageCount: 2, Model: "m2"},
				},
			})
		},
		protocol.MethodSwitchSession: func(_ any, result any) error {
			return setAppResult(result, protocol.SwitchSessionResult{Session: protocol.SessionSummary{SessionID: "s2", MessageCount: 2}})
		},
		protocol.MethodListCheckpoints: func(_ any, result any) error {
			return setAppResult(result, protocol.ListCheckpointsResult{Available: true, Checkpoints: []protocol.Checkpoint{{CheckpointID: "cp1", CreatedAt: "now", Description: "checkpoint"}}})
		},
	}}
	m := NewModel(&state.AppState{Provider: state.ProviderState{Name: "ollama", Model: "llama3.1"}}, WithRPCClient(rpc))
	next, cmd := m.Update(OpenModalMsg{Kind: ModalProviderPicker, Payload: flows.NewProviderPicker("ollama", "llama3.1")})
	m = next.(Model)
	if cmd == nil {
		t.Fatal("missing provider load cmd")
	}
	next, _ = m.Update(cmd())
	m = next.(Model)
	if view := m.View(); !strings.Contains(view, "ollama") {
		t.Fatalf("provider modal missing:\n%s", view)
	}
	next, cmd = m.Update(OpenModalMsg{Kind: ModalSessionPicker, Payload: flows.NewSessionPicker("")})
	m = next.(Model)
	if cmd == nil {
		t.Fatal("missing session load cmd")
	}
	next, _ = m.Update(cmd())
	m = next.(Model)
	next, cmd = m.Update(flows.SessionSelectedMsg{Session: protocol.SessionSummary{SessionID: "s2", MessageCount: 2}})
	m = next.(Model)
	if cmd == nil {
		t.Fatal("missing switch session cmd")
	}
	next, cmd = m.Update(cmd())
	m = next.(Model)
	if m.State.Session.ID != "s2" || m.State.Session.Turns != 2 {
		t.Fatalf("session state=%#v", m.State.Session)
	}
	if cmd == nil {
		t.Fatal("missing checkpoints cmd")
	}
	next, _ = m.Update(cmd())
	m = next.(Model)
	if len(m.State.Session.Checkpoints) != 1 || m.State.Session.Checkpoints[0].ID != "cp1" {
		t.Fatalf("checkpoints=%#v", m.State.Session.Checkpoints)
	}
	m.Store.Close()
}

func TestAppInputModalBackspaceAndFocusBranches(t *testing.T) {
	m := NewModel(nil)
	next, _ := m.Update(IntroDoneMsg{})
	m = next.(Model)
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("abc")})
	m = next.(Model)
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyBackspace})
	m = next.(Model)
	if m.Input != "ab" {
		t.Fatalf("input=%q", m.Input)
	}
	next, _ = m.Update(SwitchFocusMsg{Target: FocusChat})
	m = next.(Model)
	for _, keyType := range []tea.KeyType{tea.KeyPgUp, tea.KeyPgDown, tea.KeyHome, tea.KeyEnd} {
		next, _ = m.Update(tea.KeyMsg{Type: keyType})
		m = next.(Model)
	}
	m.openModal(ModalMention, nil)
	m.Modals.UpdateTopInput("xy")
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyBackspace})
	m = next.(Model)
	top, _ := m.Modals.Top()
	if top.Input != "x" {
		t.Fatalf("modal input=%q", top.Input)
	}
	m.openModal(ModalPalette, nil)
	m.Modals.UpdateTopInput("/unknown")
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = next.(Model)
	if m.Toast.Kind != ToastWarning {
		t.Fatalf("toast=%#v", m.Toast)
	}
	m.Store.Close()
}

func TestAppUsersRailOccupiesRight28AndClosedIsZeroFootprint(t *testing.T) {
	st := &state.AppState{Multiplayer: state.MultiplayerState{
		Enabled: true,
		Members: []state.Member{
			{ConnectionID: "c1", DisplayName: "alice", Role: "owner"},
			{ConnectionID: "c2", DisplayName: "bob", Role: "prompter", QueuePosition: 3},
			{ConnectionID: "c3", DisplayName: "carol", Role: "prompter", VotesCast: 2, VotesPending: 3},
			{ConnectionID: "c4", DisplayName: "dave", Role: "viewer", ApprovalState: "pending"},
		},
		Typing: map[string]bool{"c1": true},
	}}
	m := NewModel(st)
	next, _ := m.Update(IntroDoneMsg{})
	m = next.(Model)
	next, _ = m.Update(ResizeMsg{Width: 120, Height: 12})
	m = next.(Model)
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlU})
	m = next.(Model)
	if !m.UsersOpen || m.Regions.Chat.Width != 91 || m.Regions.Users.Width != 28 {
		t.Fatalf("regions=%#v open=%v", m.Regions, m.UsersOpen)
	}
	line := strings.Split(m.View(), "\n")[1]
	if lipgloss.Width(line) != 120 || !strings.HasSuffix(line, "users · 4                   ") {
		t.Fatalf("rail line width=%d line=%q", lipgloss.Width(line), line)
	}
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlU})
	m = next.(Model)
	if m.UsersOpen || m.Regions.Chat.Width != 120 || strings.Contains(m.View(), "users ·") {
		t.Fatalf("closed footprint open=%v regions=%#v view=%q", m.UsersOpen, m.Regions, m.View())
	}
	m.Store.Close()
}

func TestAppUsersRailDisabledNeverRenders(t *testing.T) {
	m := NewModel(&state.AppState{})
	next, _ := m.Update(IntroDoneMsg{})
	m = next.(Model)
	next, _ = m.Update(ResizeMsg{Width: 120, Height: 12})
	m = next.(Model)
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlU})
	m = next.(Model)
	if m.UsersOpen || m.Regions.Chat.Width != 120 || strings.Contains(m.View(), "users ·") {
		t.Fatalf("disabled rendered open=%v regions=%#v", m.UsersOpen, m.Regions)
	}
	m.Store.Close()
}

func TestAppUsersRailAutoHidesBelow100Cols(t *testing.T) {
	m := NewModel(&state.AppState{Multiplayer: state.MultiplayerState{
		Enabled: true,
		Members: []state.Member{{ConnectionID: "c1", DisplayName: "alice", Role: "owner"}},
	}})
	next, _ := m.Update(IntroDoneMsg{})
	m = next.(Model)
	next, _ = m.Update(ResizeMsg{Width: 120, Height: 12})
	m = next.(Model)
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlU})
	m = next.(Model)
	next, _ = m.Update(ResizeMsg{Width: 99, Height: 12})
	m = next.(Model)
	if m.UsersOpen || m.Regions.Chat.Width != 99 || !strings.Contains(m.Toast.Text, "too narrow") {
		t.Fatalf("auto-hide failed open=%v regions=%#v toast=%#v", m.UsersOpen, m.Regions, m.Toast)
	}
	m.Store.Close()
}

func waitForStore(t *testing.T, store *state.Store, ok func(state.AppState) bool) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if ok(store.Snapshot()) {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("store condition timed out")
}
