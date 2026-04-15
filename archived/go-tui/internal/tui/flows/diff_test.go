package flows

import (
	"context"
	"fmt"
	"os"
	"strings"
	"testing"

	"github.com/gongahkia/gocli-poor/internal/protocol"
)

func TestDiffListRenderCorrectWithANSI(t *testing.T) {
	body := readFixture(t, "testdata/sample.diff")
	flow := &DiffReviewFlow{
		edits: []protocol.PendingEdit{
			{
				EditID: "e1",
				Path:   "internal/foo.go",
				Hunks:  []protocol.HunkDetail{{HunkID: "h1", Header: "@@ -1,6 +1,7 @@", Body: body, Added: 3, Removed: 1}},
			},
			{
				EditID: "e2",
				Path:   "README.md",
				Hunks:  []protocol.HunkDetail{{HunkID: "h2", Header: "@@ -1 +1 @@", Body: "+hello\n", Added: 1}},
			},
		},
		open: true,
	}
	view := flow.View(72, 18)
	for _, want := range []string{"pending edits · 2", "› internal/foo.go  +3 -1", "  README.md  +1 -0", "diff · internal/foo.go", "[y] accept hunk"} {
		if !strings.Contains(view, want) {
			t.Fatalf("render missing %q\n%s", want, view)
		}
	}
	for _, want := range []string{"\x1b[36m@@ -1,6 +1,7 @@", "\x1b[32m+import \"fmt\"", "\x1b[31m-\tprintln(\"hi\")"} {
		if !strings.Contains(view, want) {
			t.Fatalf("ANSI render missing %q\n%s", want, view)
		}
	}
}

func TestDiffAcceptHunkCallsRPC(t *testing.T) {
	rpc := &mockRPC{list: protocol.DiffListResult{Edits: []protocol.DiffPreview{{
		EditID: "e1",
		Path:   "main.go",
		Hunks:  []protocol.HunkDetail{{HunkID: "h1", Header: "@@", Body: "+x\n"}},
	}}}}
	flow := NewDiffReviewFlow(rpc, true)
	if err := flow.Open(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := flow.HandleKey(context.Background(), "y"); err != nil {
		t.Fatal(err)
	}
	call := rpc.lastCall()
	if call.method != protocol.MethodAcceptHunk {
		t.Fatalf("method=%q", call.method)
	}
	params, ok := call.params.(protocol.AcceptParams)
	if !ok {
		t.Fatalf("params=%T", call.params)
	}
	if params.EditID != "e1" || params.HunkID != "h1" {
		t.Fatalf("params=%#v", params)
	}
}

func TestDiffOpenPreviewsBodylessHunk(t *testing.T) {
	rpc := &mockRPC{
		list: protocol.DiffListResult{Edits: []protocol.DiffPreview{{
			EditID: "e1",
			Path:   "main.go",
			Hunks:  []protocol.HunkDetail{{HunkID: "h1", Header: "@@"}},
		}}},
		preview: protocol.DiffPreview{
			EditID: "e1",
			Path:   "main.go",
			Hunks:  []protocol.HunkDetail{{HunkID: "h1", Header: "@@", Body: "+x\n", Added: 1}},
		},
	}
	flow := NewDiffReviewFlow(rpc, true)
	if err := flow.Open(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(rpc.calls) != 2 || rpc.calls[1].method != protocol.MethodPreviewEdit {
		t.Fatalf("calls=%#v", rpc.calls)
	}
	if !strings.Contains(flow.View(50, 12), "+x") {
		t.Fatalf("preview not rendered")
	}
}

func TestAutoAcceptSafeSkipsModal(t *testing.T) {
	rpc := &mockRPC{list: protocol.DiffListResult{Edits: []protocol.DiffPreview{{
		EditID: "e1",
		Path:   "safe.go",
		Hunks:  []protocol.HunkDetail{{HunkID: "h1", Header: "@@", Body: "+x\n", SafetyClass: "safe"}},
	}}}}
	flow := NewDiffReviewFlow(rpc, true)
	opened, err := flow.OnEditsReady(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if opened || flow.Opened() {
		t.Fatalf("safe edits opened modal")
	}
	call := rpc.lastCall()
	if call.method != protocol.MethodAcceptAll {
		t.Fatalf("method=%q", call.method)
	}
}

func TestDiffLargeHunkScrollsWindow(t *testing.T) {
	var body strings.Builder
	for i := 0; i < 1000; i++ {
		body.WriteString(fmt.Sprintf("+line-%04d\n", i))
	}
	flow := &DiffReviewFlow{
		edits: []protocol.PendingEdit{{
			EditID: "e1",
			Path:   "big.go",
			Hunks:  []protocol.HunkDetail{{HunkID: "h1", Header: "@@", Body: body.String(), Added: 1000}},
		}},
		open: true,
	}
	first := flow.View(60, 12)
	if strings.Contains(first, "+line-0900") {
		t.Fatalf("initial window rendered far content")
	}
	flow.Scroll(900)
	scrolled := flow.View(60, 12)
	if first == scrolled || !strings.Contains(scrolled, "+line-0899") {
		t.Fatalf("scroll did not change visible window")
	}
}

func readFixture(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

type rpcRecord struct {
	method string
	params any
}

type mockRPC struct {
	list          protocol.DiffListResult
	preview       protocol.DiffPreview
	calls         []rpcRecord
	notifications []rpcRecord
}

func (m *mockRPC) Call(_ context.Context, method string, params any, result any) error {
	m.calls = append(m.calls, rpcRecord{method: method, params: params})
	if method == protocol.MethodListPendingEdits {
		if out, ok := result.(*protocol.DiffListResult); ok {
			*out = m.list
		}
	}
	if method == protocol.MethodPreviewEdit {
		if out, ok := result.(*protocol.DiffPreview); ok {
			*out = m.preview
		}
	}
	return nil
}

func (m *mockRPC) Notify(_ context.Context, method string, params any) error {
	m.notifications = append(m.notifications, rpcRecord{method: method, params: params})
	return nil
}

func (m *mockRPC) lastCall() rpcRecord {
	if len(m.calls) == 0 {
		return rpcRecord{}
	}
	return m.calls[len(m.calls)-1]
}
