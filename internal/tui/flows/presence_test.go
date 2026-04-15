package flows

import (
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
)

func TestPresenceFlowDebouncesLocalTyping(t *testing.T) {
	store := state.NewStore()
	defer store.Close()
	rpc := newChatMockRPC(nil)
	now := time.Unix(100, 0)
	flow := NewPresenceFlow(Deps{RPC: rpc, Store: store, Now: func() time.Time { return now }})

	flow.Update(LocalInputChangedMsg{})
	flow.Update(LocalInputChangedMsg{})
	now = now.Add(typingDebounce - time.Millisecond)
	flow.Update(LocalInputChangedMsg{})
	now = now.Add(time.Millisecond)
	flow.Update(LocalInputChangedMsg{})
	flow.Update(widgets.SubmitMsg{Text: "done"})

	rpc.mu.Lock()
	defer rpc.mu.Unlock()
	trueCalls := 0
	falseCalls := 0
	for _, call := range rpc.notifies {
		if call.Method != protocol.MethodSetTyping {
			continue
		}
		params := call.Params.(protocol.SetTypingParams)
		if params.Typing {
			trueCalls++
		} else {
			falseCalls++
		}
	}
	if trueCalls != 2 || falseCalls != 1 {
		t.Fatalf("typing calls true=%d false=%d calls=%#v", trueCalls, falseCalls, rpc.notifies)
	}
}

func TestPresenceFlowRemoteTypingUpdatesState(t *testing.T) {
	store := state.NewStore()
	defer store.Close()
	rpc := newChatMockRPC(nil)
	flow := NewPresenceFlow(Deps{RPC: rpc, Store: store})
	if err := flow.StartFlow(nil, Deps{RPC: rpc, Store: store}); err != nil {
		t.Fatal(err)
	}
	defer flow.Stop()

	rpc.emit(protocol.MethodMemberTyping, protocol.MemberTypingNotification{ConnectionID: "c1", DisplayName: "alice", Typing: true})

	snap := store.Snapshot()
	if !snap.Multiplayer.Typing["c1"] {
		t.Fatalf("typing missing: %#v", snap.Multiplayer)
	}
	if got := widgets.TypingFooterText(snap); got != "alice is typing…" {
		t.Fatalf("footer=%q", got)
	}
}
