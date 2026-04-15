package flows

import (
	"context"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
)

type VotingFlow struct {
	rpc    RPCClient
	state  StateDispatcher
	unsubs []func()
}

func NewVotingFlow(d Deps) *VotingFlow {
	f := &VotingFlow{rpc: d.RPC, state: d.State}
	if f.state == nil && d.Store != nil {
		f.state = d.Store
	}
	return f
}

func (v *VotingFlow) Name() string { return "voting" }

func (v *VotingFlow) StartFlow(_ context.Context, d Deps) error {
	if d.RPC != nil {
		v.rpc = d.RPC
	}
	if d.State != nil {
		v.state = d.State
	} else if v.state == nil && d.Store != nil {
		v.state = d.Store
	}
	sub, _ := v.rpc.(NotificationSubscriber)
	if sub == nil {
		return nil
	}
	v.unsubs = append(v.unsubs, sub.Subscribe(protocol.MethodHunkVoteUpdated, v.onHunkVoteUpdated))
	return nil
}

func (v *VotingFlow) Stop() error {
	for _, unsub := range v.unsubs {
		unsub()
	}
	v.unsubs = nil
	return nil
}

func (v *VotingFlow) Update(tea.Msg) tea.Cmd { return nil }

func (v *VotingFlow) onHunkVoteUpdated(params any) {
	var update protocol.HunkVoteUpdate
	if !decodeNotification(params, &update) {
		return
	}
	v.dispatch(state.ActionUpdateHunkVotes{Update: update})
}

func (v *VotingFlow) dispatch(action state.Action) {
	if v.state != nil {
		v.state.Dispatch(action)
	}
}

func VoteOnHunk(ctx context.Context, rpc RPCClient, params protocol.HunkVoteParams) error {
	if ctx == nil {
		ctx = context.Background()
	}
	if rpc == nil {
		return callRPC(nil, protocol.MethodVoteOnHunk, params, nil)
	}
	return rpc.Call(ctx, protocol.MethodVoteOnHunk, params, nil)
}
