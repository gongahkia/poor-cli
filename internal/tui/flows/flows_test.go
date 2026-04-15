package flows

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
)

type pickerRPCCall struct {
	Method string
	Params any
}

type fakeRPC struct {
	calls    []pickerRPCCall
	handlers map[string]func(any, any) error
}

func (f *fakeRPC) Call(_ context.Context, method string, params any, result any) error {
	f.calls = append(f.calls, pickerRPCCall{Method: method, Params: params})
	if h := f.handlers[method]; h != nil {
		return h(params, result)
	}
	return nil
}

func setResult(dst any, src any) error {
	b, err := json.Marshal(src)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, dst)
}

func TestProviderPickerSelectCallsSwitchProvider(t *testing.T) {
	rpc := &fakeRPC{handlers: map[string]func(any, any) error{
		protocol.MethodListProviders: func(_ any, result any) error {
			return setResult(result, protocol.ListProvidersResult{
				"openai": {Available: true, Ready: true, Models: []string{"gpt-5"}},
			})
		},
		protocol.MethodSwitchProvider: func(params any, result any) error {
			want := protocol.SwitchProviderParams{Provider: "openai", Model: "gpt-5"}
			if !reflect.DeepEqual(params, want) {
				t.Fatalf("params=%#v", params)
			}
			return setResult(result, protocol.SwitchProviderResult{Success: true, Provider: protocol.ProviderInfo{Name: "openai", Model: "gpt-5"}})
		},
	}}
	p := NewProviderPicker("", "")
	loaded := FetchProvidersCmd(rpc)().(ProvidersLoadedMsg)
	p.ApplyLoaded(loaded)
	selected := p.Update(tea.KeyMsg{Type: tea.KeyEnter})().(ProviderSelectedMsg)
	switched := SwitchProviderCmd(rpc, selected.Choice, protocol.ProviderInfo{Name: "anthropic", Model: "old"})().(ProviderSwitchedMsg)
	if switched.Err != nil {
		t.Fatal(switched.Err)
	}
	if len(rpc.calls) != 2 || rpc.calls[1].Method != protocol.MethodSwitchProvider {
		t.Fatalf("calls=%#v", rpc.calls)
	}
}

func TestSessionPickerOrdersAndSwitchesSession(t *testing.T) {
	rpc := &fakeRPC{handlers: map[string]func(any, any) error{
		protocol.MethodListSessions: func(_ any, result any) error {
			return setResult(result, protocol.ListSessionsResult{Sessions: []protocol.SessionSummary{
				{SessionID: "old", UpdatedAt: 1},
				{SessionID: "new", UpdatedAt: 2},
			}})
		},
		protocol.MethodSwitchSession: func(params any, result any) error {
			if !reflect.DeepEqual(params, protocol.SwitchSessionParams{SessionID: "new"}) {
				t.Fatalf("params=%#v", params)
			}
			return setResult(result, protocol.SwitchSessionResult{Session: protocol.SessionSummary{SessionID: "new", MessageCount: 3}})
		},
	}}
	p := NewSessionPicker("")
	p.ApplyLoaded(FetchSessionsCmd(rpc)().(SessionsLoadedMsg))
	if got := p.Sessions[0].SessionID; got != "new" {
		t.Fatalf("first=%q", got)
	}
	selected := p.Update(tea.KeyMsg{Type: tea.KeyEnter})().(SessionSelectedMsg)
	switched := SwitchSessionCmd(rpc, selected.Session)().(SessionSwitchedMsg)
	if switched.Err != nil {
		t.Fatal(switched.Err)
	}
}

func TestAPIKeyPromptConcealsAndReportsReject(t *testing.T) {
	p := NewAPIKeyPrompt("openai", "")
	for _, r := range "sk-secret" {
		p.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}}, nil)
	}
	view := p.View(40, 10)
	if strings.Contains(view, "sk-secret") {
		t.Fatalf("key leaked: %q", view)
	}
	if !strings.Contains(view, "*********") {
		t.Fatalf("mask missing: %q", view)
	}
	rpc := &fakeRPC{handlers: map[string]func(any, any) error{
		protocol.MethodSetAPIKey: func(_ any, _ any) error { return errors.New("bad key") },
	}}
	msg := p.Update(tea.KeyMsg{Type: tea.KeyEnter}, rpc)().(APIKeySubmittedMsg)
	if msg.Err == nil {
		t.Fatalf("missing reject")
	}
	if !p.Persist {
		t.Fatalf("persist not defaulted on")
	}
}

func TestCostModalFetchesAndRendersDashboard(t *testing.T) {
	rpc := &fakeRPC{handlers: map[string]func(any, any) error{
		protocol.MethodCostSummary: func(_ any, result any) error {
			return setResult(result, protocol.CostSnapshot{
				Session: protocol.CostSession{TotalUSD: 0.0472, TotalTokens: map[string]int{
					"in": 12834, "out": 2104, "cached_read": 8222, "cached_write": 4190,
				}},
				LastTurn:    map[string]any{"cost_usd": 0.0083},
				PerProvider: map[string]any{"anthropic": 0.0412, "openai": 0.0060},
			})
		},
		protocol.MethodGetEconomySavings: func(_ any, result any) error {
			return setResult(result, protocol.SavingsSnapshot{CostSaved: 0.0134})
		},
	}}

	msg := FetchCostModalCmd(rpc)().(CostModalLoadedMsg)
	if msg.Err != nil {
		t.Fatal(msg.Err)
	}
	if len(rpc.calls) != 2 || rpc.calls[0].Method != protocol.MethodCostSummary || rpc.calls[1].Method != protocol.MethodGetEconomySavings {
		t.Fatalf("calls=%#v", rpc.calls)
	}
	view := msg.Payload.View(80, 20)
	for _, want := range []string{"Current turn:", "$0.0083", "anthropic", "$0.0412", "openai", "$0.0060", "Savings (economy mode): $0.0134"} {
		if !strings.Contains(view, want) {
			t.Fatalf("missing %q in %q", want, view)
		}
	}
}
