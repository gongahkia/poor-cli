package flows

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
)

func TestPermissionPromptDecisionSendsNotification(t *testing.T) {
	rpc := &mockRPC{}
	flow := NewPermissionFlow(rpc, 30*time.Second)
	flow.Open(protocol.PermissionReq{
		RequestID:  "r1",
		RequestKey: "k1",
		PromptID:   "p1",
		ToolName:   "bash",
		Rationale:  "install dev dependency",
		ToolArgs:   map[string]any{"command": "npm install -D vitest"},
	}, time.Now())
	if err := flow.HandleKey(context.Background(), "A"); err != nil {
		t.Fatal(err)
	}
	if flow.Opened() {
		t.Fatalf("permission modal remained open")
	}
	if len(rpc.notifications) != 1 {
		t.Fatalf("notifications=%d", len(rpc.notifications))
	}
	n := rpc.notifications[0]
	if n.method != protocol.MethodPermissionRes {
		t.Fatalf("method=%q", n.method)
	}
	res, ok := n.params.(protocol.PermissionRes)
	if !ok {
		t.Fatalf("params=%T", n.params)
	}
	if res.RequestID != "r1" || res.RequestKey != "k1" || res.Decision != "allow" || res.RememberScope != "once" || res.Allowed == nil || !*res.Allowed {
		t.Fatalf("res=%#v", res)
	}
}

func TestPermissionTimeoutVisualIndicator(t *testing.T) {
	flow := NewPermissionFlow(&mockRPC{}, 30*time.Second)
	start := time.Unix(100, 0)
	flow.Open(protocol.PermissionReq{
		RequestID: "r1",
		ToolName:  "bash",
		Rationale: "install dev dependency",
		ToolArgs:  map[string]any{"command": "npm install -D vitest"},
	}, start)
	view := flow.View(72, 14, start.Add(10*time.Second))
	for _, want := range []string{"Permission requested", "Tool: bash", "Rationale: install dev dependency", "npm install -D vitest", "timeout: 20s", "[A] allow once"} {
		if !strings.Contains(view, want) {
			t.Fatalf("render missing %q\n%s", want, view)
		}
	}
	if !strings.Contains(view, "########") || !strings.Contains(view, "----") {
		t.Fatalf("countdown bar missing mixed fill\n%s", view)
	}
}

func TestPermissionExpiredDecisionDoesNotNotify(t *testing.T) {
	rpc := &mockRPC{}
	flow := NewPermissionFlow(rpc, time.Nanosecond)
	flow.Open(protocol.PermissionReq{RequestID: "r1", ToolName: "bash"}, time.Now().Add(-time.Second))
	if err := flow.HandleKey(context.Background(), "D"); err != ErrPermissionTimedOut {
		t.Fatalf("err=%v", err)
	}
	if len(rpc.notifications) != 0 {
		t.Fatalf("sent notification after timeout")
	}
}
