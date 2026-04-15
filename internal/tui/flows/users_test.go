package flows

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
)

type usersRPC struct {
	calls    []usersCall
	handlers map[string][]NotificationHandler
}

type usersCall struct {
	method string
	params any
}

func (r *usersRPC) Call(_ context.Context, method string, params any, result any) error {
	r.calls = append(r.calls, usersCall{method: method, params: params})
	switch method {
	case protocol.MethodListHostMembers:
		return copyJSON(result, protocol.HostMembersResult{
			Running: true,
			Rooms: []protocol.RoomSnapshot{{
				Name: "dev",
				Members: []protocol.MultiplayerMember{{
					ConnectionID:  "c1",
					DisplayName:   "alice",
					Role:          "viewer",
					ApprovalState: "approved",
				}},
			}},
		})
	case protocol.MethodListPresence:
		return copyJSON(result, protocol.PresenceResult{Room: "dev", Presence: map[string]bool{"c1": true}})
	case protocol.MethodListRoomQueue:
		return copyJSON(result, protocol.RoomQueueResult{Room: "dev", Snapshot: []protocol.QueueItem{{ConnectionID: "c1", Position: 2}}})
	default:
		return copyJSON(result, protocol.MemberActionResult{Success: true})
	}
}

func (r *usersRPC) Subscribe(method string, handler NotificationHandler) func() {
	if r.handlers == nil {
		r.handlers = map[string][]NotificationHandler{}
	}
	r.handlers[method] = append(r.handlers[method], handler)
	return func() {}
}

func (r *usersRPC) emit(method string, params any) {
	for _, handler := range r.handlers[method] {
		handler(params)
	}
}

func TestUsersFlowTypingNotificationUpdatesState(t *testing.T) {
	store := state.NewStoreWithState(state.AppState{Multiplayer: state.MultiplayerState{
		Enabled: true,
		Members: []state.Member{{ConnectionID: "c1", DisplayName: "alice", Role: "viewer"}},
	}})
	defer store.Close()
	rpc := &usersRPC{}
	flow := NewUsersFlow(Deps{RPC: rpc, Store: store, State: store, Now: func() time.Time {
		return time.Unix(7, 0)
	}})
	if err := flow.StartFlow(context.Background(), Deps{}); err != nil {
		t.Fatal(err)
	}
	rpc.emit(protocol.MethodMemberTyping, protocol.MemberTypingNotification{ConnectionID: "c1", Typing: true})
	got := store.Snapshot().Multiplayer
	if !got.Typing["c1"] || !got.PresenceAt.Equal(time.Unix(7, 0)) {
		t.Fatalf("typing not updated: %#v", got)
	}
}

func TestUsersFlowApproveDispatchesRPCAndToast(t *testing.T) {
	store := state.NewStoreWithState(state.AppState{Multiplayer: state.MultiplayerState{Enabled: true, RoomName: "dev"}})
	defer store.Close()
	rpc := &usersRPC{}
	flow := NewUsersFlow(Deps{RPC: rpc, Store: store, State: store})
	cmd := flow.Approve(state.Member{ConnectionID: "c1"})
	if cmd == nil {
		t.Fatal("missing cmd")
	}
	cmd()
	if len(rpc.calls) == 0 || rpc.calls[0].method != protocol.MethodApproveHostMember {
		t.Fatalf("calls=%#v", rpc.calls)
	}
	params := rpc.calls[0].params.(protocol.MemberActionParams)
	if params.ConnectionID != "c1" || params.Room != "dev" {
		t.Fatalf("params=%#v", params)
	}
	snap := store.Snapshot()
	if len(snap.Toasts) == 0 || snap.Toasts[len(snap.Toasts)-1].Kind != state.ToastSuccess {
		t.Fatalf("toasts=%#v", snap.Toasts)
	}
}

func copyJSON(dst any, src any) error {
	b, err := json.Marshal(src)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, dst)
}
