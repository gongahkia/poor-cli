package widgets

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/gongahkia/gocli-poor/internal/markdown"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
)

func TestChatStreamingPaint(t *testing.T) {
	c := testChat()
	c.SetMessages([]state.Message{{ID: "a1", Role: state.RoleAssistant, RequestID: "r1", Streaming: true}})
	for i := 0; i < 100; i++ {
		c.AppendChunk("r1", "x")
	}
	got := c.View(24, 6)
	want := strings.Join([]string{
		"           xxxxxxxxxxxxx",
		"           xxxxxxxxxxxxx",
		"           xxxxxxxxxxxxx",
		"           xxxxxxxxxxxxx",
		"           xxxxxxxxxxxxx",
		"           xxxxxxxxx",
	}, "\n")
	if got != want {
		t.Fatalf("view mismatch:\n%s", got)
	}
	if !c.IsAtBottom() {
		t.Fatalf("not at bottom after stream")
	}
}

func TestChatResizePreservesScrollAnchor(t *testing.T) {
	c := testChat()
	c.SetMessages(manyMessages(20))
	_ = c.View(20, 5)
	c.ScrollDown(6)
	before := c.visibleRows()[0]
	_ = c.View(30, 5)
	_ = c.View(16, 5)
	after := c.visibleRows()[0]
	if before != after {
		t.Fatalf("anchor changed: %q -> %q", before, after)
	}
}

func TestChatAutoscrollAppend(t *testing.T) {
	c := testChat()
	c.SetMessages([]state.Message{{ID: "a1", Role: state.RoleAssistant, RequestID: "r1", Streaming: true, Content: strings.Repeat("a", 40)}})
	_ = c.View(20, 3)
	c.ScrollToBottom()
	c.AppendChunk("r1", strings.Repeat("b", 20))
	if !c.IsAtBottom() {
		t.Fatalf("append at bottom did not autoscroll")
	}
	c.ScrollUp(1)
	top := c.absoluteTop()
	c.AppendChunk("r1", strings.Repeat("c", 20))
	if c.absoluteTop() != top {
		t.Fatalf("append while detached moved viewport: %d -> %d", top, c.absoluteTop())
	}
}

func TestChatLongMessageWrapsRunewidth(t *testing.T) {
	c := testChat()
	c.SetMessages([]state.Message{{ID: "u1", Role: state.RoleUser, Content: strings.Repeat("界", 12)}})
	got := c.View(12, 6)
	want := strings.Join([]string{
		"you › 界界界",
		"      界界界",
		"      界界界",
		"      界界界",
		"",
		"",
	}, "\n")
	if got != want {
		t.Fatalf("wrap mismatch:\n%s", got)
	}
}

func TestChatRemoteAuthorPrefix(t *testing.T) {
	c := testChat()
	c.SetMultiplayer(state.MultiplayerState{Enabled: true, LocalConnectionID: "c2"})
	c.SetMessages([]state.Message{
		{ID: "u1", Role: state.RoleUser, Content: "remote", AuthorConnectionID: "c1", AuthorDisplayName: "alice"},
		{ID: "u2", Role: state.RoleUser, Content: "local", AuthorConnectionID: "c2", AuthorDisplayName: "bob"},
		{ID: "a1", Role: state.RoleAssistant, Content: "answer", AuthorConnectionID: "c1", AuthorDisplayName: "alice"},
	})
	got := c.View(40, 6)
	for _, want := range []string{"alice › remote", "you › local", "poor-cli · replying to alice answer"} {
		if !strings.Contains(got, want) {
			t.Fatalf("missing %q in:\n%s", want, got)
		}
	}
	if strings.Contains(got, "bob ›") {
		t.Fatalf("local display name leaked:\n%s", got)
	}
}

func TestToolBlockToggles(t *testing.T) {
	c := testChat()
	c.SetMessages([]state.Message{{
		ID:   "t1",
		Role: state.RoleTool,
		ToolCalls: []state.ToolCall{{
			EventID:       "e1",
			ToolName:      "bash",
			Status:        "ok",
			ArgsPreview:   "command=git status",
			ResultPreview: "clean",
		}},
	}})
	collapsed := c.View(40, 5)
	if strings.Contains(collapsed, "output:") || !strings.Contains(collapsed, "▸ bash · ok") || !strings.Contains(collapsed, "└─ command=git status") {
		t.Fatalf("collapsed output visible:\n%s", collapsed)
	}
	_, _ = c.Update(tea.KeyMsg{Type: tea.KeySpace})
	expanded := c.View(40, 5)
	if !strings.Contains(expanded, "▾ bash · ok") || !strings.Contains(expanded, "output:") || !strings.Contains(expanded, "clean") {
		t.Fatalf("expanded output missing:\n%s", expanded)
	}
}

func TestChatWaitingResponseGlyph(t *testing.T) {
	c := testChat()
	c.SetMessages([]state.Message{{ID: "a1", Role: state.RoleAssistant, RequestID: "r1", Streaming: true}})
	got := c.View(24, 2)
	if !strings.Contains(got, "poor-cli › ·") {
		t.Fatalf("waiting glyph missing:\n%s", got)
	}
}

func testChat() *ChatView {
	t := theme.DarkWithCapability(theme.CapabilityMonochrome)
	return NewChat(&t, markdown.NewPlainRenderer())
}

func manyMessages(n int) []state.Message {
	msgs := make([]state.Message, 0, n)
	for i := 0; i < n; i++ {
		msgs = append(msgs, state.Message{ID: string(rune('a' + i)), Role: state.RoleUser, Content: "line"})
	}
	return msgs
}
