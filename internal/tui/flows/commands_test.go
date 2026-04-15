package flows

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets/commands"
)

func TestCommandClearEmptiesMessages(t *testing.T) {
	store := state.NewStore()
	t.Cleanup(store.Close)
	store.Dispatch(state.ActionAppendMessage{Msg: state.Message{ID: "m1", Role: state.RoleUser, Content: "hi"}})

	msg := run(t, NewCommandsFlow(Deps{State: store}).Dispatch("/clear", ""))

	if got := store.Snapshot().Messages; len(got) != 0 {
		t.Fatalf("messages not cleared: %#v", got)
	}
	toast, ok := msg.(ToastMsg)
	if !ok || toast.Kind != ToastSuccess {
		t.Fatalf("wrong msg: %#v", msg)
	}
}

func TestCommandModelSwitchProviderArgs(t *testing.T) {
	rpc := &commandMockRPC{}
	store := &mockState{}
	flow := NewCommandsFlow(Deps{RPC: rpc, State: store})

	msg := run(t, flow.DispatchSelect(widgets.SelectCommandMsg{CommandID: "/model", Args: "claude-4-6-haiku"}))

	requireCall(t, rpc, protocol.MethodSwitchProvider, protocol.SwitchProviderParams{Provider: "", Model: "claude-4-6-haiku"})
	if len(store.actions) != 1 {
		t.Fatalf("provider action count=%d", len(store.actions))
	}
	if _, ok := store.actions[0].(state.ActionSetProvider); !ok {
		t.Fatalf("wrong action: %#v", store.actions[0])
	}
	toast, ok := msg.(ToastMsg)
	if !ok || toast.Kind != ToastSuccess {
		t.Fatalf("wrong msg: %#v", msg)
	}
}

func TestCommandSwitchErrorToasts(t *testing.T) {
	rpc := &commandMockRPC{errs: map[string]error{protocol.MethodSwitchProvider: errors.New("boom")}}
	flow := NewCommandsFlow(Deps{RPC: rpc})

	msg := run(t, flow.Dispatch("/model", "claude-4-6-haiku"))

	toast, ok := msg.(ToastMsg)
	if !ok {
		t.Fatalf("wrong msg: %#v", msg)
	}
	if toast.Kind != ToastError || !strings.Contains(toast.Text, "boom") {
		t.Fatalf("wrong toast: %#v", toast)
	}
}

func TestCommandUnknownToasts(t *testing.T) {
	msg := run(t, NewCommandsFlow(Deps{}).Dispatch("/foo", ""))

	toast, ok := msg.(ToastMsg)
	if !ok {
		t.Fatalf("wrong msg: %#v", msg)
	}
	if toast.Kind != ToastError || toast.Text != "unknown command: /foo" {
		t.Fatalf("wrong toast: %#v", toast)
	}
}

func TestServerBackedCommandsRoute(t *testing.T) {
	cases := []struct {
		name       string
		commandID  string
		args       string
		method     string
		wantParams any
	}{
		{name: "compact", commandID: "/compact", method: protocol.MethodClearHistory},
		{name: "provider picker", commandID: "/provider", method: protocol.MethodListProviders},
		{name: "provider switch", commandID: "/provider", args: "anthropic", method: protocol.MethodSwitchProvider, wantParams: protocol.SwitchProviderParams{Provider: "anthropic"}},
		{name: "model", commandID: "/model", args: "claude-4-6-haiku", method: protocol.MethodSwitchProvider, wantParams: protocol.SwitchProviderParams{Model: "claude-4-6-haiku"}},
		{name: "session picker", commandID: "/session", method: protocol.MethodListSessions},
		{name: "sessions alias", commandID: "/sessions", method: protocol.MethodListSessions},
		{name: "session switch", commandID: "/session", args: "s1", method: protocol.MethodSwitchSession, wantParams: protocol.SwitchSessionParams{SessionID: "s1"}},
		{name: "diff", commandID: "/diff", method: protocol.MethodListPendingEdits, wantParams: protocol.DiffListParams{}},
		{name: "watch", commandID: "/watch", method: protocol.MethodContextStatus},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rpc := &commandMockRPC{}
			msg := run(t, NewCommandsFlow(Deps{RPC: rpc}).Dispatch(tc.commandID, tc.args))

			requireCall(t, rpc, tc.method, tc.wantParams)
			if msg == nil {
				t.Fatalf("nil msg")
			}
		})
	}
}

func TestCommandCostFetchesDashboard(t *testing.T) {
	rpc := &commandMockRPC{}
	msg := run(t, NewCommandsFlow(Deps{RPC: rpc}).Dispatch("/cost", ""))

	if len(rpc.calls) < 2 {
		t.Fatalf("calls=%#v", rpc.calls)
	}
	if rpc.calls[0].method != protocol.MethodCostSummary || rpc.calls[1].method != protocol.MethodGetEconomySavings {
		t.Fatalf("calls=%#v", rpc.calls)
	}
	open, ok := msg.(OpenModalMsg)
	if !ok || open.Kind != ModalCost {
		t.Fatalf("wrong msg: %#v", msg)
	}
	payload, ok := open.Payload.(CostPayload)
	if !ok {
		t.Fatalf("payload=%T", open.Payload)
	}
	view := payload.View(80, 20)
	if !strings.Contains(view, "anthropic") || !strings.Contains(view, "Savings") {
		t.Fatalf("view=%q", view)
	}
}

func TestClientCommandsRoute(t *testing.T) {
	flow := NewCommandsFlow(Deps{})

	help := run(t, flow.Dispatch("/help", ""))
	open, ok := help.(OpenModalMsg)
	if !ok || open.Kind != ModalHelp {
		t.Fatalf("wrong help msg: %#v", help)
	}

	quit := run(t, flow.Dispatch("/quit", ""))
	if _, ok := quit.(tea.QuitMsg); !ok {
		t.Fatalf("wrong quit msg: %#v", quit)
	}
}

func TestCustomCommandsSyncAndRoute(t *testing.T) {
	rpc := &commandMockRPC{}
	registry := commands.NewRegistry()
	flow := NewCommandsFlow(Deps{RPC: rpc, Registry: registry})

	run(t, flow.SyncCustomCommands())
	run(t, flow.Dispatch("/deploy", "--prod"))

	if !hasCommand(registry.All(), "/deploy") {
		t.Fatalf("custom command not registered: %#v", registry.All())
	}
	requireCall(t, rpc, protocol.MethodRunCustomCommand, map[string]any{"name": "deploy", "argsText": "--prod"})
}

type commandRPCCall struct {
	method string
	params any
}

type commandMockRPC struct {
	calls []commandRPCCall
	errs  map[string]error
}

func (m *commandMockRPC) Call(ctx context.Context, method string, params any, result any) error {
	m.calls = append(m.calls, commandRPCCall{method: method, params: params})
	if err := m.errs[method]; err != nil {
		return err
	}
	switch out := result.(type) {
	case *protocol.SwitchProviderResult:
		*out = protocol.SwitchProviderResult{
			Success:  true,
			Provider: protocol.ProviderInfo{Name: "anthropic", Model: "claude-4-6-haiku"},
		}
	case *protocol.SwitchSessionResult:
		*out = protocol.SwitchSessionResult{Session: protocol.SessionSummary{SessionID: "s1"}}
	case *protocol.ListProvidersResult:
		*out = protocol.ListProvidersResult{"anthropic": {Ready: true, Models: []string{"claude-4-6-haiku"}}}
	case *protocol.ListSessionsResult:
		*out = protocol.ListSessionsResult{Sessions: []protocol.SessionSummary{{SessionID: "s1"}}, ActiveSessionID: "s1"}
	case *protocol.CostSnapshot:
		*out = protocol.CostSnapshot{
			Session:     protocol.CostSession{TotalUSD: 0.12, TotalTokens: map[string]int{"in": 12834, "out": 2104}},
			PerProvider: map[string]any{"anthropic": 0.12},
		}
	case *protocol.SavingsSnapshot:
		*out = protocol.SavingsSnapshot{CostSaved: 0.0134}
	case *protocol.DiffListResult:
		*out = protocol.DiffListResult{Edits: []protocol.DiffPreview{{EditID: "e1", Path: "main.go"}}}
	case *map[string]any:
		*out = map[string]any{"ok": true}
	case *customCommandList:
		out.CommandsRaw = []customCommand{{Name: "deploy", Description: "Deploy service"}}
	}
	return nil
}

type mockState struct {
	actions []state.Action
}

func (m *mockState) Dispatch(action state.Action) {
	m.actions = append(m.actions, action)
}

func run(t *testing.T, cmd tea.Cmd) tea.Msg {
	t.Helper()
	if cmd == nil {
		t.Fatalf("nil cmd")
	}
	return cmd()
}

func requireCall(t *testing.T, rpc *commandMockRPC, method string, params any) {
	t.Helper()
	if len(rpc.calls) == 0 {
		t.Fatalf("no rpc calls")
	}
	got := rpc.calls[len(rpc.calls)-1]
	if got.method != method {
		t.Fatalf("method=%q want %q", got.method, method)
	}
	if params == nil {
		if got.params != nil {
			t.Fatalf("params=%#v want nil", got.params)
		}
		return
	}
	if !reflect.DeepEqual(got.params, params) {
		t.Fatalf("params=%#v want %#v", got.params, params)
	}
}

func hasCommand(cmds []commands.Command, id string) bool {
	for _, cmd := range cmds {
		if cmd.ID == id {
			return true
		}
	}
	return false
}
