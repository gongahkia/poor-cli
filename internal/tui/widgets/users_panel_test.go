package widgets

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/state"
)

func TestUsersPanelGoldenRender(t *testing.T) {
	panel := NewUsersPanel(nil)
	panel.SetState(state.MultiplayerState{
		Enabled: true,
		Members: []state.Member{
			{ConnectionID: "c1", DisplayName: "alice", Role: "owner"},
			{ConnectionID: "c2", DisplayName: "bob", Role: "prompter", QueuePosition: 3},
			{ConnectionID: "c3", DisplayName: "carol", Role: "prompter", VotesCast: 2, VotesPending: 3},
			{ConnectionID: "c4", DisplayName: "dave", Role: "viewer", ApprovalState: "pending"},
		},
		Typing: map[string]bool{"c1": true},
	})
	got := panel.View(UsersPanelWidth, 9)
	want := strings.Join([]string{
		"users · 4                   ",
		">alice                 owner",
		"  ● typing                  ",
		" bob                prompter",
		"  #3 queue                  ",
		" carol              prompter",
		"  voted 2/3                 ",
		" dave                 viewer",
		"  pending                   ",
	}, "\n")
	if got != want {
		t.Fatalf("render mismatch\nwant:\n%q\ngot:\n%q", want, got)
	}
	for _, line := range strings.Split(got, "\n") {
		if lipgloss.Width(line) != UsersPanelWidth {
			t.Fatalf("line width=%d line=%q", lipgloss.Width(line), line)
		}
	}
}

func TestUsersPanelTruncatesNamesTo16(t *testing.T) {
	panel := NewUsersPanel(nil)
	panel.SetState(state.MultiplayerState{
		Enabled: true,
		Members: []state.Member{{
			ConnectionID: "c1",
			DisplayName:  "abcdefghijklmnopXYZ",
			Role:         "viewer",
		}},
	})
	view := panel.View(UsersPanelWidth, 3)
	if strings.Contains(view, "XYZ") || !strings.Contains(view, "abcdefghijklmnop") {
		t.Fatalf("name not truncated to 16 cols:\n%s", view)
	}
}
