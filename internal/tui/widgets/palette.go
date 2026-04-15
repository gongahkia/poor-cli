package widgets

import (
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets/commands"
)

const (
	defaultPaletteWidth  = 48
	defaultPaletteHeight = 10
)

type SelectCommandMsg struct {
	CommandID string
	Args      string
}

type ClosePaletteMsg struct {
	Residual string
}

type ProviderChangedMsg struct{}

type FetchCustomCommandsMsg struct{}

type CustomCommandsLoadedMsg struct {
	Commands []commands.Command
}

type Palette struct {
	theme    theme.Theme
	registry *commands.Registry
	input    string
	items    []commands.Command
	selected int
	width    int
	height   int
	open     bool
}

func NewPalette(th theme.Theme, registry *commands.Registry) *Palette {
	if registry == nil {
		registry = commands.NewRegistry()
	}
	p := &Palette{
		theme:    th,
		registry: registry,
		input:    "/",
		width:    defaultPaletteWidth,
		height:   defaultPaletteHeight,
		open:     true,
	}
	p.refresh()
	return p
}

func (p *Palette) Update(msg tea.Msg) tea.Cmd {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		p.SetSize(msg.Width, p.height)
	case ProviderChangedMsg:
		p.refresh()
		return emitPalette(FetchCustomCommandsMsg{})
	case CustomCommandsLoadedMsg:
		p.registry.SetCustoms(msg.Commands)
		p.refresh()
	case tea.KeyMsg:
		return p.updateKey(msg)
	}
	return nil
}

func (p *Palette) View() string {
	width := max(1, p.width)
	height := max(1, p.height)
	bodyHeight := max(1, height-1)
	lines := []string{"› " + p.input}
	if len(p.items) == 0 {
		lines = append(lines, fitPalette("  no commands", width-2))
	} else {
		for i, cmd := range p.items {
			if i >= bodyHeight {
				break
			}
			marker := " "
			style := p.theme.Palette
			if i == p.selected {
				marker = "›"
				style = p.theme.PaletteHighlight
			}
			line := fitPalette(marker+" "+cmd.Icon+" "+cmd.Label+"  "+cmd.Description, width-2)
			lines = append(lines, style.Render(line))
		}
	}
	for len(lines) < height {
		lines = append(lines, "")
	}
	if len(lines) > height {
		lines = lines[:height]
	}
	return strings.Join(lines, "\n")
}

func (p *Palette) SetSize(width, height int) {
	if width > 0 {
		p.width = width
	}
	if height > 0 {
		p.height = height
	}
}

func (p *Palette) Input() string {
	return p.input
}

func (p *Palette) Commands() []commands.Command {
	out := make([]commands.Command, len(p.items))
	copy(out, p.items)
	return out
}

func (p *Palette) Selected() int {
	return p.selected
}

func (p *Palette) Open() bool {
	return p.open
}

func (p *Palette) updateKey(msg tea.KeyMsg) tea.Cmd {
	switch msg.String() {
	case "esc", "ctrl+c":
		p.open = false
		return emitPalette(ClosePaletteMsg{Residual: p.input})
	case "enter":
		if len(p.items) == 0 {
			return nil
		}
		cmd := p.items[p.selected]
		args := commandArgs(p.input)
		p.open = false
		return emitPalette(SelectCommandMsg{CommandID: cmd.ID, Args: args})
	case "up", "ctrl+p":
		if p.selected > 0 {
			p.selected--
		}
	case "down", "ctrl+n":
		if p.selected < len(p.items)-1 {
			p.selected++
		}
	case "backspace":
		p.backspace()
	default:
		if msg.Type == tea.KeyRunes {
			p.input += string(msg.Runes)
		}
	}
	p.refresh()
	return nil
}

func (p *Palette) backspace() {
	if p.input == "" {
		return
	}
	runes := []rune(p.input)
	p.input = string(runes[:len(runes)-1])
}

func (p *Palette) refresh() {
	p.items = p.registry.Filter(commandToken(p.input))
	if p.selected >= len(p.items) {
		p.selected = max(0, len(p.items)-1)
	}
}

func commandToken(input string) string {
	input = strings.TrimSpace(input)
	if input == "" {
		return ""
	}
	return strings.Fields(input)[0]
}

func commandArgs(input string) string {
	fields := strings.Fields(input)
	if len(fields) <= 1 {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(input, fields[0]))
}

func emitPalette(msg tea.Msg) tea.Cmd {
	return func() tea.Msg {
		return msg
	}
}

func fitPalette(line string, width int) string {
	if width <= 0 {
		return ""
	}
	for lipgloss.Width(line) > width && len([]rune(line)) > 0 {
		runes := []rune(line)
		line = string(runes[:len(runes)-1])
	}
	return line
}
