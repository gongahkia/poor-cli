package widgets

import (
	"strings"

	keybind "github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/config"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/mattn/go-runewidth"
	"github.com/rivo/uniseg"
)

const maxInputBytes = 64 * 1024

type SubmitMsg struct {
	Text string
}

type CancelMsg struct{}

type PaletteOpenMsg struct {
	Prefix string
}

type MentionOpenMsg struct {
	Prefix    string
	CursorPos int
}

type MentionCloseMsg struct{}

type InputDeps struct {
	Theme   *theme.Theme
	Keymap  *config.Keymap
	History *History
}

type InputField struct {
	theme   *theme.Theme
	km      *config.Keymap
	history *History
	buf     []string
	cursor  int
	focused bool
}

func NewInput(th *theme.Theme, km *config.Keymap) *InputField {
	return NewInputField(InputDeps{Theme: th, Keymap: km})
}

func NewInputField(d InputDeps) *InputField {
	return &InputField{
		theme:   d.Theme,
		km:      defaultKeymap(d.Keymap),
		history: d.History,
		focused: true,
	}
}

func (i *InputField) Update(msg tea.Msg) (*InputField, tea.Cmd) {
	if i == nil {
		return i, nil
	}
	k, ok := msg.(tea.KeyMsg)
	if !ok || !i.focused {
		return i, nil
	}
	if k.Paste {
		i.insert(string(k.Runes))
		return i, nil
	}
	switch {
	case i.isSubmit(k):
		text := i.Value()
		i.Clear()
		if i.history != nil && text != "" {
			i.history.Push(text)
		}
		return i, emitInput(SubmitMsg{Text: text})
	case i.isCancel(k):
		return i, emitInput(CancelMsg{})
	case i.isPalette(k):
		if i.paletteRune(k) && !(i.Value() == "" && i.cursor == 0) {
			i.insert(string(k.Runes))
			return i, nil
		}
		return i, emitInput(PaletteOpenMsg{Prefix: i.Value()})
	case i.isMention(k):
		if k.Type == tea.KeyRunes && string(k.Runes) == "@" {
			i.insert("@")
		}
		return i, emitInput(MentionOpenMsg{Prefix: i.mentionPrefix(), CursorPos: i.CursorPos()})
	}
	switch k.Type {
	case tea.KeyEnter:
		i.insert("\n")
	case tea.KeyBackspace, tea.KeyCtrlH:
		i.backspace()
	case tea.KeyDelete:
		i.delete()
	case tea.KeyLeft:
		i.move(-1)
	case tea.KeyRight:
		i.move(1)
	case tea.KeyHome:
		i.cursor = 0
	case tea.KeyEnd:
		i.cursor = len(i.buf)
	case tea.KeyUp:
		if i.history != nil && (i.history.cursor != -1 || i.Value() == "" || i.cursor == 0) {
			if s, ok := i.history.Prev(); ok {
				i.SetValue(s)
			}
		}
	case tea.KeyDown:
		if i.history != nil {
			if s, ok := i.history.Next(); ok {
				i.SetValue(s)
			}
		}
	case tea.KeyRunes:
		i.insert(string(k.Runes))
		if strings.ContainsRune(string(k.Runes), '@') || i.mentionActive() {
			return i, emitInput(MentionOpenMsg{Prefix: i.mentionPrefix(), CursorPos: i.CursorPos()})
		}
	}
	return i, nil
}

func (i *InputField) View(width int) string {
	if i == nil {
		return ""
	}
	style := lipgloss.NewStyle()
	if i.theme != nil {
		if i.focused {
			style = i.theme.InputFieldFocused
		} else {
			style = i.theme.InputField
		}
	}
	frame := style.GetHorizontalFrameSize()
	contentWidth := width - frame
	if contentWidth < 1 {
		contentWidth = 1
	}
	lines := wrapDisplay(i.displayClusters(), contentWidth)
	return style.Width(contentWidth).Render(strings.Join(lines, "\n"))
}

func (i *InputField) Focus() {
	if i != nil {
		i.focused = true
	}
}

func (i *InputField) Blur() {
	if i != nil {
		i.focused = false
	}
}

func (i *InputField) Value() string {
	if i == nil {
		return ""
	}
	return strings.Join(i.buf, "")
}

func (i *InputField) SetValue(s string) {
	if i == nil {
		return
	}
	i.buf = splitClusters(s)
	i.cursor = len(i.buf)
}

func (i *InputField) Clear() {
	if i == nil {
		return
	}
	i.buf = nil
	i.cursor = 0
	if i.history != nil {
		i.history.Reset()
	}
}

func (i *InputField) InsertAt(s string) {
	if i != nil {
		i.insert(s)
	}
}

func (i *InputField) InsertAtPos(pos int, s string) {
	if i == nil {
		return
	}
	i.cursor = clamp(pos, 0, len(i.buf))
	i.insert(s)
}

func (i *InputField) CursorPos() int {
	if i == nil {
		return 0
	}
	return i.cursor
}

func (i *InputField) History() *History {
	if i == nil {
		return nil
	}
	return i.history
}

func (i *InputField) insert(s string) {
	if s == "" || len(i.Value())+len(s) > maxInputBytes {
		return
	}
	clusters := splitClusters(s)
	next := make([]string, 0, len(i.buf)+len(clusters))
	next = append(next, i.buf[:i.cursor]...)
	next = append(next, clusters...)
	next = append(next, i.buf[i.cursor:]...)
	i.buf = next
	i.cursor += len(clusters)
	if i.history != nil {
		i.history.Reset()
	}
}

func (i *InputField) backspace() {
	if i.cursor == 0 {
		return
	}
	i.buf = append(i.buf[:i.cursor-1], i.buf[i.cursor:]...)
	i.cursor--
}

func (i *InputField) delete() {
	if i.cursor >= len(i.buf) {
		return
	}
	i.buf = append(i.buf[:i.cursor], i.buf[i.cursor+1:]...)
}

func (i *InputField) move(delta int) {
	i.cursor = clamp(i.cursor+delta, 0, len(i.buf))
}

func (i *InputField) isSubmit(k tea.KeyMsg) bool {
	return keybind.Matches(k, i.km.Submit) || k.String() == "ctrl+enter" || (k.String() == "ctrl+j" && bindingHas(i.km.Submit, "ctrl+enter"))
}

func (i *InputField) isCancel(k tea.KeyMsg) bool {
	return keybind.Matches(k, i.km.Cancel)
}

func (i *InputField) isPalette(k tea.KeyMsg) bool {
	return keybind.Matches(k, i.km.Palette)
}

func (i *InputField) isMention(k tea.KeyMsg) bool {
	if k.Type == tea.KeyRunes && string(k.Runes) != "@" {
		return false
	}
	return keybind.Matches(k, i.km.Mention)
}

func (i *InputField) paletteRune(k tea.KeyMsg) bool {
	return k.Type == tea.KeyRunes && string(k.Runes) == "/"
}

func (i *InputField) mentionPrefix() string {
	if i == nil || i.cursor == 0 {
		return ""
	}
	for n := i.cursor - 1; n >= 0; n-- {
		switch i.buf[n] {
		case "@":
			return strings.Join(i.buf[n+1:i.cursor], "")
		case " ", "\n", "\t":
			return ""
		}
	}
	return ""
}

func (i *InputField) mentionActive() bool {
	if i == nil || i.cursor == 0 {
		return false
	}
	for n := i.cursor - 1; n >= 0; n-- {
		switch i.buf[n] {
		case "@":
			return true
		case " ", "\n", "\t":
			return false
		}
	}
	return false
}

func (i *InputField) displayClusters() []string {
	out := make([]string, 0, len(i.buf)+1)
	for n, c := range i.buf {
		if n == i.cursor && i.focused {
			out = append(out, "·")
		}
		out = append(out, c)
	}
	if i.cursor == len(i.buf) && i.focused {
		out = append(out, "·")
	}
	if len(out) == 1 && out[0] == "·" {
		return []string{"› ·"}
	}
	return out
}

func wrapDisplay(clusters []string, width int) []string {
	if width < 1 {
		width = 1
	}
	var lines []string
	var b strings.Builder
	col := 0
	for _, c := range clusters {
		if c == "\n" {
			lines = append(lines, b.String())
			b.Reset()
			col = 0
			continue
		}
		w := runewidth.StringWidth(c)
		if w == 0 {
			b.WriteString(c)
			continue
		}
		if col > 0 && col+w > width {
			lines = append(lines, b.String())
			b.Reset()
			col = 0
		}
		b.WriteString(c)
		col += w
	}
	lines = append(lines, b.String())
	return lines
}

func splitClusters(s string) []string {
	g := uniseg.NewGraphemes(s)
	var out []string
	for g.Next() {
		out = append(out, g.Str())
	}
	return out
}

func defaultKeymap(km *config.Keymap) *config.Keymap {
	if km != nil {
		return km
	}
	km, err := config.NewKeymap(config.DefaultConfig())
	if err != nil {
		return &config.Keymap{}
	}
	return km
}

func bindingHas(b keybind.Binding, want string) bool {
	for _, k := range b.Keys() {
		if k == want {
			return true
		}
	}
	return false
}

func emitInput(msg tea.Msg) tea.Cmd {
	return func() tea.Msg { return msg }
}

func clamp(v, min, max int) int {
	if v < min {
		return min
	}
	if v > max {
		return max
	}
	return v
}
