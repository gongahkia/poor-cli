package widgets

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/config"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets/commands"
)

func TestTopBarGitBranchDirAndFile(t *testing.T) {
	repo := t.TempDir()
	if err := os.MkdirAll(filepath.Join(repo, ".git"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(repo, ".git", "HEAD"), []byte("ref: refs/heads/main\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if view := NewTopBar(TopBarDeps{Title: "poor", Version: "v1", Cwd: repo}).View(80); !strings.Contains(view, "main") || !strings.Contains(view, "poor v1") {
		t.Fatalf("view=%q", view)
	}
	worktree := t.TempDir()
	gitDir := filepath.Join(t.TempDir(), "actual.git")
	if err := os.MkdirAll(gitDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(gitDir, "HEAD"), []byte("abcdef1234567890"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(worktree, ".git"), []byte("gitdir: "+gitDir+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if view := NewTopBar(TopBarDeps{Cwd: worktree}).View(80); !strings.Contains(view, "abcdef1") {
		t.Fatalf("worktree view=%q", view)
	}
}

func TestPaletteUpdateSelectCloseAndResize(t *testing.T) {
	tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
	reg := commands.NewRegistry()
	p := NewPalette(tm, reg)
	p.Update(tea.WindowSizeMsg{Width: 32, Height: 8})
	p.Update(CustomCommandsLoadedMsg{Commands: []commands.Command{{ID: "deploy", Description: "Deploy"}}})
	p.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("dep")})
	if !strings.Contains(p.View(), "deploy") || p.Input() != "/dep" || len(p.Commands()) == 0 {
		t.Fatalf("palette state input=%q view=%q", p.Input(), p.View())
	}
	p.Update(tea.KeyMsg{Type: tea.KeyBackspace})
	p.Update(tea.KeyMsg{Type: tea.KeyDown})
	p.Update(tea.KeyMsg{Type: tea.KeyUp})
	if p.Selected() != 0 {
		t.Fatalf("selected=%d", p.Selected())
	}
	msg := p.Update(tea.KeyMsg{Type: tea.KeyEnter})().(SelectCommandMsg)
	if msg.CommandID != "/deploy" {
		t.Fatalf("msg=%#v", msg)
	}
	p = NewPalette(tm, reg)
	closeMsg := p.Update(tea.KeyMsg{Type: tea.KeyEsc})().(ClosePaletteMsg)
	if p.Open() || closeMsg.Residual == "" {
		t.Fatalf("close open=%v msg=%#v", p.Open(), closeMsg)
	}
	if msg := p.Update(ProviderChangedMsg{})().(FetchCustomCommandsMsg); (msg != FetchCustomCommandsMsg{}) {
		t.Fatalf("provider changed msg=%#v", msg)
	}
}

func TestInputFocusEditHistoryAndMentions(t *testing.T) {
	hist := NewHistory("", 2)
	km, err := config.NewKeymap(config.DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	input := NewInput(nil, km)
	input.history = hist
	input.Blur()
	input.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("ignored")})
	if input.Value() != "" {
		t.Fatalf("blur accepted input")
	}
	input.Focus()
	input.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("abc")})
	input.Update(tea.KeyMsg{Type: tea.KeyLeft})
	input.Update(tea.KeyMsg{Type: tea.KeyDelete})
	input.InsertAtPos(1, "Z")
	if input.Value() != "aZb" || input.CursorPos() != 2 || input.History() == nil {
		t.Fatalf("input=%q cursor=%d", input.Value(), input.CursorPos())
	}
	if view := input.View(4); view == "" {
		t.Fatal("empty view")
	}
	input.SetValue("first")
	_, cmd := input.Update(tea.KeyMsg{Type: tea.KeyCtrlJ})
	msg := cmd().(SubmitMsg)
	if msg.Text != "first" || input.Value() != "" || len(hist.Entries()) != 1 {
		t.Fatalf("submit msg=%#v entries=%#v", msg, hist.Entries())
	}
	input.Update(tea.KeyMsg{Type: tea.KeyUp})
	if input.Value() != "first" {
		t.Fatalf("history prev=%q", input.Value())
	}
	input.Update(tea.KeyMsg{Type: tea.KeyDown})
	if input.Value() != "" {
		t.Fatalf("history next=%q", input.Value())
	}
	input.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("@file")})
	if _, cmd := input.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("@")}); cmd == nil {
		t.Fatal("mention cmd missing")
	}
}

func TestMentionPickerStatePreviewAndKeys(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "main.go"), []byte("package main\nfunc main() {}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	p := NewMentionPicker(&state.AppState{FileCatalog: state.FileCatalog{Files: []state.FileCatalogFile{{Path: "main.go"}, {Path: "README.md"}, {Path: "main.go"}}}}, WithRepoRoot(root))
	cmd := p.Open("@ma")
	if cmd == nil {
		t.Fatal("preview cmd missing")
	}
	p.Update(cmd())
	if view := p.View(50, 8); !strings.Contains(view, "main.go") || !strings.Contains(view, "package main") {
		t.Fatalf("mention view=%q", view)
	}
	p.Update(tea.KeyMsg{Type: tea.KeyDown})
	p.Update(tea.KeyMsg{Type: tea.KeyUp})
	p.Update(tea.KeyMsg{Type: tea.KeyBackspace})
	p.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("e")})
	if msg := p.Update(tea.KeyMsg{Type: tea.KeyEnter})().(SelectMentionMsg); msg.Path == "" {
		t.Fatalf("select msg=%#v", msg)
	}
	p.SetFiles([]string{"a.go", "a.go", ""})
	p.SetState(&state.AppState{FileCatalog: state.FileCatalog{Files: []state.FileCatalogFile{{Path: "b.go"}}}})
	p.Open("@a")
	if len(p.Matches()) != 1 || p.SelectedPath() != "a.go" {
		t.Fatalf("matches=%#v selected=%q", p.Matches(), p.SelectedPath())
	}
	if msg := p.Update(tea.KeyMsg{Type: tea.KeyEsc})().(MentionCloseMsg); (msg != MentionCloseMsg{}) {
		t.Fatalf("close msg=%#v", msg)
	}
	outside := NewMentionPicker(nil, WithRepoRoot(root))
	outside.SetFiles([]string{"../x"})
	outside.Open("@")
	outside.Update(MentionPreviewLoadedMsg{Path: "../x", Err: os.ErrPermission})
	if view := outside.View(40, 5); !strings.Contains(view, "permission") {
		t.Fatalf("err view=%q", view)
	}
	if _, err := outside.readPreviewFile("../x"); err == nil {
		t.Fatal("expected outside repo error")
	}
	if NewRegistry() == nil {
		t.Fatal("nil command registry")
	}
}

func TestStatusBarAndToolMessageEdges(t *testing.T) {
	store := state.NewStoreWithState(state.AppState{
		Connection:      state.ConnState{Phase: state.Error},
		Provider:        state.ProviderState{Name: "ollama", Model: "llama3.1"},
		Session:         state.SessionState{ID: "session-long-id"},
		ContextPressure: state.ContextPressure{Tokens: 9, Budget: 10},
		Cost:            state.CostState{TotalUSD: 0.001, InputTokens: 3, OutputTokens: 4},
	})
	defer store.Close()
	bar := NewStatusBar(StatusBarDeps{Store: store})
	defer bar.Close()
	if view := bar.View(24); !strings.Contains(view, "$0.0010") {
		t.Fatalf("status=%q", view)
	}
	chat := New(nil, nil)
	chat.SetMessages([]state.Message{{
		ID:   "m1",
		Role: state.RoleAssistant,
		ToolCalls: []state.ToolCall{{
			ToolName:      "bash",
			Status:        "error",
			ArgsPreview:   strings.Repeat("x", 40),
			ResultPreview: "line1\nline2",
			Error:         "bad",
		}},
	}})
	if view := chat.View(40, 6); !strings.Contains(view, "bash") || !strings.Contains(view, "error") {
		t.Fatalf("chat tool view=%q", view)
	}
	chat.Update(tea.KeyMsg{Type: tea.KeyEnter})
	chat.ScrollToTop()
}
