package flows

import (
	"context"
	"regexp"
	"strings"
	"testing"

	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
)

func TestVoteRowRendersStatusesAndOwnerOnly(t *testing.T) {
	cases := []struct {
		name string
		hunk protocol.HunkDetail
		want string
		hide bool
	}{
		{
			name: "pending",
			hunk: protocol.HunkDetail{
				HunkID:        "h1",
				Header:        "@@",
				Body:          "+x\n",
				VoteStatus:    "pending",
				VoteThreshold: "majority",
				Votes: protocol.HunkVotes{
					{DisplayName: "alice", Decision: "approve"},
					{DisplayName: "carol", Decision: "approve"},
					{DisplayName: "bob", Decision: "reject"},
				},
			},
			want: "votes · ✓ alice, carol · ✗ bob · pending (majority)",
		},
		{
			name: "approved",
			hunk: protocol.HunkDetail{
				HunkID:         "h1",
				Header:         "@@",
				Body:           "+x\n",
				VoteStatus:     "approved",
				VoteThreshold:  "unanimous",
				RequiredVoters: 3,
				Votes: protocol.HunkVotes{
					{DisplayName: "alice", Decision: "approve"},
					{DisplayName: "bob", Decision: "approve"},
					{DisplayName: "carol", Decision: "approve"},
				},
			},
			want: "votes · ✓ 3/3 · approved",
		},
		{
			name: "rejected",
			hunk: protocol.HunkDetail{
				HunkID:        "h1",
				Header:        "@@",
				Body:          "+x\n",
				VoteStatus:    "rejected",
				VoteThreshold: "majority",
				Votes: protocol.HunkVotes{
					{DisplayName: "alice", Decision: "reject"},
					{DisplayName: "bob", Decision: "reject"},
					{DisplayName: "carol", Decision: "approve"},
				},
			},
			want: "votes · ✗ 2/3 · rejected",
		},
		{
			name: "owner_only",
			hunk: protocol.HunkDetail{HunkID: "h1", Header: "@@", Body: "+x\n", VoteStatus: "pending", VoteThreshold: "owner_only"},
			hide: true,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			flow := &DiffReviewFlow{edits: []protocol.PendingEdit{{EditID: "e1", Path: "main.go", Hunks: []protocol.HunkDetail{tc.hunk}}}, open: true}
			view := stripANSI(flow.View(80, 12))
			if tc.hide {
				if strings.Contains(view, "votes") {
					t.Fatalf("vote row visible:\n%s", view)
				}
				return
			}
			if !strings.Contains(view, tc.want) {
				t.Fatalf("missing %q:\n%s", tc.want, view)
			}
			if count := strings.Count(view, "votes"); count != 1 {
				t.Fatalf("vote rows=%d:\n%s", count, view)
			}
		})
	}
}

func TestPendingVoteBlocksAcceptAndToastsOnce(t *testing.T) {
	rpc := &mockRPC{list: protocol.DiffListResult{Edits: []protocol.DiffPreview{{
		EditID: "e1",
		Path:   "main.go",
		Hunks: []protocol.HunkDetail{{
			HunkID: "h1", Header: "@@", Body: "+x\n", VoteStatus: "pending", VoteThreshold: "majority",
		}},
	}}}}
	rec := &actionRecorder{}
	flow := NewDiffReviewFlow(rpc, false)
	flow.SetStateDispatcher(rec)
	if err := flow.Open(context.Background()); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		if err := flow.HandleKey(context.Background(), "y"); err != nil {
			t.Fatal(err)
		}
	}
	if call := rpc.lastCall(); call.method == protocol.MethodAcceptHunk {
		t.Fatalf("accept was not blocked")
	}
	toastActions := rec.ofType(func(action state.Action) bool {
		_, ok := action.(state.ActionToast)
		return ok
	})
	if len(toastActions) != 1 || toastActions[0].(state.ActionToast).Text != "needs vote threshold" {
		t.Fatalf("toasts=%#v", toastActions)
	}
}

func TestVoteClearUsesRPCAndNotificationRemovesTally(t *testing.T) {
	rpc := &mockRPC{list: protocol.DiffListResult{Edits: []protocol.DiffPreview{{
		EditID: "e1",
		Path:   "main.go",
		Hunks: []protocol.HunkDetail{{
			HunkID:        "h1",
			Header:        "@@",
			Body:          "+x\n",
			VoteStatus:    "approved",
			VoteThreshold: "majority",
			Votes: protocol.HunkVotes{
				{ConnectionID: "alice", DisplayName: "alice", Decision: "approve"},
				{ConnectionID: "me", DisplayName: "me", Decision: "approve"},
			},
		}},
	}}}}
	flow := NewDiffReviewFlow(rpc, false)
	if err := flow.Open(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := flow.HandleKey(context.Background(), "vc"); err != nil {
		t.Fatal(err)
	}
	call := rpc.lastCall()
	if call.method != protocol.MethodVoteOnHunk {
		t.Fatalf("method=%q", call.method)
	}
	params, ok := call.params.(protocol.HunkVoteParams)
	if !ok || params.Decision != "clear" || params.EditID != "e1" || params.HunkID != "h1" {
		t.Fatalf("params=%#v", call.params)
	}
	flow.ApplyHunkVoteUpdate(protocol.HunkVoteUpdate{
		EditID:         "e1",
		HunkID:         "h1",
		Status:         "pending",
		Threshold:      "majority",
		RequiredVoters: 2,
		Votes:          protocol.HunkVotes{{ConnectionID: "alice", DisplayName: "alice", Decision: "approve"}},
	})
	view := stripANSI(flow.View(80, 12))
	if strings.Contains(view, "me") || !strings.Contains(view, "✓ alice") {
		t.Fatalf("vote update not applied:\n%s", view)
	}
}

func TestVotingFlowSubscribesAndDispatches(t *testing.T) {
	rpc := &mockNotifyRPC{}
	rec := &actionRecorder{}
	flow := NewVotingFlow(Deps{RPC: rpc, State: rec})
	if err := flow.StartFlow(context.Background(), Deps{}); err != nil {
		t.Fatal(err)
	}
	rpc.emit(protocol.MethodHunkVoteUpdated, map[string]any{
		"editId":    "e1",
		"hunkId":    "h1",
		"status":    "approved",
		"threshold": "majority",
		"votes": []map[string]any{
			{"connectionId": "alice", "displayName": "alice", "decision": "approve"},
		},
	})
	actions := rec.ofType(func(action state.Action) bool {
		_, ok := action.(state.ActionUpdateHunkVotes)
		return ok
	})
	if len(actions) != 1 {
		t.Fatalf("actions=%#v", rec.actions)
	}
	update := actions[0].(state.ActionUpdateHunkVotes)
	if update.Update.HunkID != "h1" || len(update.Update.Votes) != 1 || update.Update.Votes[0].DisplayName != "alice" {
		t.Fatalf("update=%#v", update)
	}
}

func stripANSI(s string) string {
	return regexp.MustCompile(`\x1b\[[0-9;]*m`).ReplaceAllString(s, "")
}
