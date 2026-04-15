package widgets

import (
	"bufio"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/sahilm/fuzzy"
)

const (
	mentionMaxRows      = 10
	mentionPreviewLines = 5
)

type FetchFileCatalogMsg struct{}

type SelectMentionMsg struct {
	Path string
}

type MentionPreviewLoadedMsg struct {
	Path  string
	Lines []string
	Err   error
}

type PreviewReader func(path string) ([]string, error)

type MentionOption func(*MentionPicker)

func WithRepoRoot(root string) MentionOption {
	return func(p *MentionPicker) {
		p.repoRoot = root
		p.readPreview = p.readPreviewFile
	}
}

func WithPreviewReader(reader PreviewReader) MentionOption {
	return func(p *MentionPicker) {
		p.readPreview = reader
	}
}

type MentionPicker struct {
	state          *state.AppState
	repoRoot       string
	open           bool
	loaded         bool
	loading        bool
	query          string
	files          []string
	matches        []MentionMatch
	selected       int
	preview        map[string][]string
	previewLoading map[string]bool
	previewErr     map[string]error
	readPreview    PreviewReader
}

type MentionMatch struct {
	Path  string
	Score int
}

func NewMentionPicker(appState *state.AppState, opts ...MentionOption) *MentionPicker {
	p := &MentionPicker{
		state:          appState,
		repoRoot:       ".",
		preview:        make(map[string][]string),
		previewLoading: make(map[string]bool),
		previewErr:     make(map[string]error),
	}
	p.readPreview = p.readPreviewFile
	for _, opt := range opts {
		opt(p)
	}
	return p
}

func (p *MentionPicker) Open(prefix string) tea.Cmd {
	p.open = true
	p.query = strings.TrimPrefix(prefix, "@")
	var cmds []tea.Cmd
	if !p.loaded {
		p.loadFromState()
		if len(p.files) == 0 {
			p.loading = true
			cmds = append(cmds, func() tea.Msg { return FetchFileCatalogMsg{} })
		}
	}
	p.refreshMatches()
	cmds = append(cmds, p.ensurePreviewCmd())
	return mentionBatch(cmds...)
}

func (p *MentionPicker) Close() {
	p.open = false
}

func (p *MentionPicker) SetState(appState *state.AppState) {
	p.state = appState
	if !p.loaded || len(p.files) == 0 {
		p.loadFromState()
		p.refreshMatches()
	}
}

func (p *MentionPicker) SetFiles(files []string) {
	p.files = uniqueStrings(files)
	p.loaded = true
	p.loading = false
	p.refreshMatches()
}

func (p *MentionPicker) Matches() []MentionMatch {
	out := make([]MentionMatch, len(p.matches))
	copy(out, p.matches)
	return out
}

func (p *MentionPicker) SelectedPath() string {
	if p.selected < 0 || p.selected >= len(p.matches) {
		return ""
	}
	return p.matches[p.selected].Path
}

func (p *MentionPicker) Update(msg tea.Msg) tea.Cmd {
	switch msg := msg.(type) {
	case MentionOpenMsg:
		return p.Open(msg.Prefix)
	case MentionPreviewLoadedMsg:
		p.previewLoading[msg.Path] = false
		if msg.Err != nil {
			p.previewErr[msg.Path] = msg.Err
			return nil
		}
		p.preview[msg.Path] = firstLines(msg.Lines, mentionPreviewLines)
		delete(p.previewErr, msg.Path)
		return nil
	case tea.KeyMsg:
		return p.updateKey(msg)
	default:
		return nil
	}
}

func (p *MentionPicker) updateKey(msg tea.KeyMsg) tea.Cmd {
	if !p.open {
		return nil
	}
	switch msg.String() {
	case "esc":
		p.Close()
		return func() tea.Msg { return MentionCloseMsg{} }
	case "up", "ctrl+p":
		if p.selected > 0 {
			p.selected--
		}
		return p.ensurePreviewCmd()
	case "down", "ctrl+n":
		if p.selected < len(p.matches)-1 {
			p.selected++
		}
		return p.ensurePreviewCmd()
	case "enter":
		path := p.SelectedPath()
		if path == "" {
			return nil
		}
		p.Close()
		return func() tea.Msg { return SelectMentionMsg{Path: path} }
	case "backspace":
		if p.query == "" {
			return nil
		}
		runes := []rune(p.query)
		p.query = string(runes[:len(runes)-1])
		p.refreshMatches()
		return p.ensurePreviewCmd()
	}
	if msg.Type != tea.KeyRunes {
		return nil
	}
	p.query += string(msg.Runes)
	p.refreshMatches()
	return p.ensurePreviewCmd()
}

func (p *MentionPicker) View(width, height int) string {
	if !p.open {
		return ""
	}
	width = max(1, width)
	height = max(1, height)
	leftWidth := max(1, width/2)
	rightWidth := max(1, width-leftWidth)
	rows := p.visibleRows(height)
	left := []string{"@ files", "@" + p.query}
	if p.loading {
		left = append(left, "loading files...")
	} else if len(p.matches) == 0 {
		left = append(left, "no matches")
	} else {
		for i := 0; i < rows; i++ {
			m := p.matches[i]
			prefix := "  "
			if i == p.selected {
				prefix = "> "
			}
			left = append(left, prefix+m.Path)
		}
	}
	right := p.previewLines()
	lines := make([]string, max(len(left), len(right)))
	for i := range lines {
		l, r := "", ""
		if i < len(left) {
			l = left[i]
		}
		if i < len(right) {
			r = right[i]
		}
		lines[i] = mentionFit(l, leftWidth) + mentionFit(r, rightWidth)
	}
	body := strings.Join(firstLines(lines, height), "\n")
	return lipgloss.NewStyle().Width(width).Height(height).Render(body)
}

func (p *MentionPicker) loadFromState() {
	if p.state == nil {
		return
	}
	files := make([]string, 0, len(p.state.FileCatalog.Files))
	for _, file := range p.state.FileCatalog.Files {
		if file.Path != "" {
			files = append(files, file.Path)
		}
	}
	p.files = uniqueStrings(files)
	p.loaded = len(p.files) > 0
	p.loading = p.state.FileCatalog.Loading
}

func (p *MentionPicker) refreshMatches() {
	p.matches = rankMentionMatches(p.query, p.files)
	if p.selected >= len(p.matches) {
		p.selected = len(p.matches) - 1
	}
	if p.selected < 0 {
		p.selected = 0
	}
}

func rankMentionMatches(query string, files []string) []MentionMatch {
	query = strings.TrimPrefix(strings.ToLower(strings.TrimSpace(query)), "@")
	if query == "" {
		out := make([]MentionMatch, 0, len(files))
		for i, path := range files {
			out = append(out, MentionMatch{Path: path, Score: -i})
		}
		return out
	}
	fuzzyMatches := fuzzy.Find(query, files)
	out := make([]MentionMatch, 0, len(fuzzyMatches))
	for _, match := range fuzzyMatches {
		path := files[match.Index]
		out = append(out, MentionMatch{Path: path, Score: mentionScore(query, path, match.Score)})
	}
	sort.SliceStable(out, func(i, j int) bool {
		ib, jb := filepath.Base(out[i].Path), filepath.Base(out[j].Path)
		if ib == jb && len(out[i].Path) != len(out[j].Path) {
			return len(out[i].Path) < len(out[j].Path)
		}
		if out[i].Score != out[j].Score {
			return out[i].Score > out[j].Score
		}
		if len(out[i].Path) != len(out[j].Path) {
			return len(out[i].Path) < len(out[j].Path)
		}
		return out[i].Path < out[j].Path
	})
	return out
}

func mentionScore(query, path string, fuzzyScore int) int {
	lowerPath := strings.ToLower(path)
	base := strings.ToLower(filepath.Base(path))
	stem := strings.TrimSuffix(base, filepath.Ext(base))
	score := fuzzyScore
	if strings.Contains(lowerPath, query) {
		score += 3000
	}
	if strings.Contains(base, query) {
		score += 2000
	}
	if stem == query {
		score += 1000
	}
	return score
}

func (p *MentionPicker) ensurePreviewCmd() tea.Cmd {
	path := p.SelectedPath()
	if path == "" || p.readPreview == nil {
		return nil
	}
	if _, ok := p.preview[path]; ok {
		return nil
	}
	if p.previewLoading[path] {
		return nil
	}
	p.previewLoading[path] = true
	return func() tea.Msg {
		lines, err := p.readPreview(path)
		return MentionPreviewLoadedMsg{Path: path, Lines: firstLines(lines, mentionPreviewLines), Err: err}
	}
}

func (p *MentionPicker) previewLines() []string {
	path := p.SelectedPath()
	if path == "" {
		return []string{"Preview:"}
	}
	out := []string{"Preview:"}
	if p.previewLoading[path] {
		return append(out, "loading...")
	}
	if err := p.previewErr[path]; err != nil {
		return append(out, err.Error())
	}
	lines := p.preview[path]
	if len(lines) == 0 {
		return append(out, "")
	}
	return append(out, lines...)
}

func (p *MentionPicker) readPreviewFile(path string) ([]string, error) {
	fullPath := path
	if !filepath.IsAbs(path) {
		fullPath = filepath.Join(p.repoRoot, path)
	}
	cleanRoot, err := filepath.Abs(p.repoRoot)
	if err != nil {
		return nil, err
	}
	cleanPath, err := filepath.Abs(filepath.Clean(fullPath))
	if err != nil {
		return nil, err
	}
	rel, err := filepath.Rel(cleanRoot, cleanPath)
	if err != nil {
		return nil, err
	}
	if strings.HasPrefix(rel, ".."+string(os.PathSeparator)) || rel == ".." {
		return nil, errors.New("preview outside repo")
	}
	file, err := os.Open(cleanPath)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	var lines []string
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
		if len(lines) == mentionPreviewLines {
			break
		}
	}
	return lines, scanner.Err()
}

func (p *MentionPicker) visibleRows(height int) int {
	room := max(1, height-2)
	return min(min(len(p.matches), mentionMaxRows), room)
}

func uniqueStrings(in []string) []string {
	seen := make(map[string]struct{}, len(in))
	out := make([]string, 0, len(in))
	for _, s := range in {
		if s == "" {
			continue
		}
		if _, ok := seen[s]; ok {
			continue
		}
		seen[s] = struct{}{}
		out = append(out, s)
	}
	return out
}

func firstLines(lines []string, n int) []string {
	if len(lines) <= n {
		out := make([]string, len(lines))
		copy(out, lines)
		return out
	}
	out := make([]string, n)
	copy(out, lines[:n])
	return out
}

func mentionFit(line string, width int) string {
	if width <= 0 {
		return ""
	}
	if lipgloss.Width(line) > width {
		runes := []rune(line)
		for lipgloss.Width(string(runes)) > width && len(runes) > 0 {
			runes = runes[:len(runes)-1]
		}
		line = string(runes)
	}
	return line + strings.Repeat(" ", width-lipgloss.Width(line))
}

func mentionBatch(cmds ...tea.Cmd) tea.Cmd {
	out := cmds[:0]
	for _, cmd := range cmds {
		if cmd != nil {
			out = append(out, cmd)
		}
	}
	switch len(out) {
	case 0:
		return nil
	case 1:
		return out[0]
	default:
		return tea.Batch(out...)
	}
}
