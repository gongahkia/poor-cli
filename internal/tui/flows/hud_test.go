package flows

import (
	"strings"
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
)

func TestHudFlowThrottlesCostUpdates(t *testing.T) {
	rec := &actionRecorder{}
	now := time.Unix(10, 0)
	hud := NewHudFlow(Deps{State: rec, Now: func() time.Time { return now }})

	for i := range 100 {
		hud.onCostUpdate(protocol.CostUpdate{InputTokens: i, OutputTokens: i + 1, EstimatedCost: float64(i) / 1000})
	}
	if len(rec.actions) != 0 {
		t.Fatalf("actions before tick=%d", len(rec.actions))
	}
	hud.Update(hudTickMsg{})
	hud.Update(hudTickMsg{})

	updates := rec.ofType(func(a state.Action) bool {
		_, ok := a.(state.ActionUpdateCost)
		return ok
	})
	if len(updates) != 1 {
		t.Fatalf("updates=%#v", updates)
	}
	got := updates[0].(state.ActionUpdateCost)
	if got.Snapshot.InputTokens != 99 || got.Snapshot.OutputTokens != 100 {
		t.Fatalf("snapshot=%#v", got.Snapshot)
	}
}

func TestHudFlowContextPressureWarnsAt80(t *testing.T) {
	rec := &actionRecorder{}
	hud := NewHudFlow(Deps{State: rec})

	hud.onContextPressure(protocol.ContextPressure{UsedTokens: 79, MaxTokens: 100, PressurePct: 79})
	hud.onContextPressure(protocol.ContextPressure{UsedTokens: 81, MaxTokens: 100, PressurePct: 81})

	var toasts []state.Action
	for _, action := range rec.actions {
		if toast, ok := action.(state.ActionToast); ok {
			toasts = append(toasts, toast)
		}
	}
	if len(toasts) != 1 {
		t.Fatalf("toasts=%#v", toasts)
	}
	toast := toasts[0].(state.ActionToast)
	if toast.Kind != state.ToastWarning || !strings.Contains(toast.Text, "80") {
		t.Fatalf("toast=%#v", toast)
	}
}

type actionRecorder struct {
	actions []state.Action
}

func (r *actionRecorder) Dispatch(action state.Action) {
	r.actions = append(r.actions, action)
}

func (r *actionRecorder) ofType(match func(state.Action) bool) []state.Action {
	out := make([]state.Action, 0)
	for _, action := range r.actions {
		if match(action) {
			out = append(out, action)
		}
	}
	return out
}
