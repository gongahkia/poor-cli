package widgets

import (
	"reflect"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/state"
)

func TestMentionMatchingOrder(t *testing.T) {
	p := pickerWithFiles([]string{
		"poor-cli/server/handlers/chat_streaming.py",
		"docs/changelog.md",
		"nvim-poor-cli/lua/poor-cli/chat.lua",
		"poor-cli/server/handlers/chat.py",
	})
	p.Open("@chat")

	got := paths(p.Matches()[:2])
	want := []string{"poor-cli/server/handlers/chat.py", "nvim-poor-cli/lua/poor-cli/chat.lua"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("top matches: got %v want %v", got, want)
	}
}

func TestMentionDisambiguatesSharedBasenameByShorterPath(t *testing.T) {
	p := pickerWithFiles([]string{
		"apps/web/server/handlers/chat.py",
		"src/chat.py",
		"server/chat_streaming.py",
	})
	p.Open("@chat")

	got := paths(p.Matches()[:2])
	want := []string{"src/chat.py", "apps/web/server/handlers/chat.py"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("shared basename order: got %v want %v", got, want)
	}
}

func TestMentionPreviewLoadsFirstFiveLinesLazily(t *testing.T) {
	calls := 0
	p := pickerWithFiles([]string{"src/chat.py"})
	p.readPreview = func(path string) ([]string, error) {
		calls++
		return []string{"one", "two", "three", "four", "five", "six"}, nil
	}

	cmd := p.Open("@chat")
	if calls != 0 {
		t.Fatalf("preview loaded before cmd ran")
	}
	msg := cmd()
	if calls != 1 {
		t.Fatalf("preview calls: got %d want 1", calls)
	}
	p.Update(msg)

	got := p.preview["src/chat.py"]
	want := []string{"one", "two", "three", "four", "five"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("preview lines: got %v want %v", got, want)
	}
	if view := p.View(80, 12); contains(view, "six") {
		t.Fatalf("preview included sixth line: %q", view)
	}
}

func TestMentionOpenWithEmptyCatalogRequestsFetch(t *testing.T) {
	st := state.AppState{}
	p := NewMentionPicker(&st)

	cmd := p.Open("@chat")
	if _, ok := cmd().(FetchFileCatalogMsg); !ok {
		t.Fatalf("open did not request catalog fetch")
	}
}

func pickerWithFiles(files []string) *MentionPicker {
	st := state.AppState{FileCatalog: state.FileCatalog{}}
	for _, file := range files {
		st.FileCatalog.Files = append(st.FileCatalog.Files, state.FileCatalogFile{Path: file})
	}
	p := NewMentionPicker(&st, WithPreviewReader(func(string) ([]string, error) { return nil, nil }))
	return p
}

func paths(matches []MentionMatch) []string {
	out := make([]string, len(matches))
	for i, match := range matches {
		out[i] = match.Path
	}
	return out
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

var _ tea.Msg = SelectMentionMsg{}
