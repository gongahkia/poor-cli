package flows

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/gongahkia/gocli-poor/internal/protocol"
)

func TestDiffRejectRegenNavigationAndFallbackBodies(t *testing.T) {
	rpc := &mockRPC{list: protocol.DiffListResult{Edits: []protocol.DiffPreview{
		{
			EditIDLegacy: "legacy-edit",
			Path:         "a.go",
			Hunks: []protocol.HunkDetail{
				{HunkIDLegacy: "legacy-hunk", Header: "@@ -1 +1 @@", Before: "old\n", After: "new\n", Added: 1, Removed: 1},
				{HunkID: "h2", Header: "@@", Body: "+second\n", Added: 1},
			},
		},
		{
			EditID: "e2",
			Path:   "b.go",
			Hunks:  []protocol.HunkDetail{{HunkID: "h3", Body: "@@ -1 +1 @@\n-x\n+y\n", Added: 1, Removed: 1}},
		},
	}}}
	flow := NewDiffReviewFlow(rpc, false)
	if err := flow.Open(context.Background()); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"down", "up", "right", "left", "pgdown", "pgup", "home", "end"} {
		if err := flow.HandleKey(context.Background(), key); err != nil {
			t.Fatalf("%s: %v", key, err)
		}
	}
	if view := flow.View(60, 14); !strings.Contains(view, "+new") {
		t.Fatalf("fallback body missing:\n%s", view)
	}
	if err := flow.HandleKey(context.Background(), "n"); err != nil {
		t.Fatal(err)
	}
	if call := rpc.lastCall(); call.method != protocol.MethodRejectHunk {
		t.Fatalf("reject call=%#v", call)
	}
	if err := flow.HandleKey(context.Background(), "r"); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"f", "i", "x", "backspace", "!"} {
		if err := flow.HandleKey(context.Background(), key); err != nil {
			t.Fatalf("regen key %q: %v", key, err)
		}
	}
	if !strings.Contains(flow.View(60, 14), "regen instruction: fi!") {
		t.Fatalf("regen view missing:\n%s", flow.View(60, 14))
	}
	if err := flow.HandleKey(context.Background(), "enter"); err != nil {
		t.Fatal(err)
	}
	if call := rpc.lastCall(); call.method != protocol.MethodRegenerateHunk {
		t.Fatalf("regen call=%#v", call)
	}
	if len(flow.Edits()) == 0 {
		t.Fatal("edits clone empty")
	}
	if err := flow.HandleKey(context.Background(), "Y"); err != nil {
		t.Fatal(err)
	}
	if flow.Opened() {
		t.Fatal("accept all did not close")
	}
	rpc.list.Edits = []protocol.DiffPreview{{EditID: "e3", Hunks: []protocol.HunkDetail{{HunkID: "h4"}}}}
	if err := flow.HandleKey(context.Background(), "N"); err != nil {
		t.Fatal(err)
	}
	if call := rpc.lastCall(); call.method != protocol.MethodRejectAll {
		t.Fatalf("reject all call=%#v", call)
	}
}

func TestDiffNoPendingAndNilRPC(t *testing.T) {
	if err := NewDiffReviewFlow(&mockRPC{}, false).Open(context.Background()); !errors.Is(err, ErrNoPendingEdits) {
		t.Fatalf("err=%v", err)
	}
	if err := NewDiffReviewFlow(nil, false).AcceptHunk(context.Background()); !errors.Is(err, ErrNoPendingEdits) {
		t.Fatalf("accept err=%v", err)
	}
	flow := &DiffReviewFlow{edits: []protocol.PendingEdit{{EditID: "e1", Hunks: []protocol.HunkDetail{{HunkID: "h1"}}}}, open: true}
	if err := flow.AcceptHunk(context.Background()); err == nil || !strings.Contains(err.Error(), "nil rpc") {
		t.Fatalf("nil rpc err=%v", err)
	}
}
