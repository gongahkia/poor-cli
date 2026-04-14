package tui

import (
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/state"
)

const defaultIntroVersion = "v0.0.0"

type Model struct {
	State            *state.AppState
	Width            int
	Height           int
	Regions          Regions
	Focus            FocusRouter
	Modals           ModalStack
	Input            string
	ChatScrollAnchor int
	Toast            ToastMsg
	Intro            IntroModel
	connectCmd       tea.Cmd
}

type Option func(*Model)

func WithConnectCmd(cmd tea.Cmd) Option {
	return func(m *Model) {
		m.connectCmd = cmd
	}
}

func WithIntroVersion(version string) Option {
	return func(m *Model) {
		m.Intro.Version = version
	}
}

func NewModel(appState *state.AppState, opts ...Option) Model {
	m := Model{
		State:  appState,
		Focus:  FocusRouter{Target: FocusIntro},
		Intro:  IntroModel{Active: true, Version: defaultIntroVersion},
		Width:  80,
		Height: 24,
	}
	for _, opt := range opts {
		opt(&m)
	}
	m.relayout()
	return m
}

func NewProgram(appState *state.AppState, opts ...Option) *tea.Program {
	return tea.NewProgram(NewModel(appState, opts...), tea.WithAltScreen(), tea.WithMouseCellMotion())
}

func Run(appState *state.AppState, opts ...Option) error {
	_, err := NewProgram(appState, opts...).Run()
	return err
}

func (m Model) Init() tea.Cmd {
	return tea.Batch(m.connectCmd, tea.EnableBracketedPaste, introTimeoutCmd())
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.resize(msg.Width, msg.Height)
		return m, nil
	case ResizeMsg:
		m.resize(msg.Width, msg.Height)
		return m, nil
	case IntroDoneMsg:
		m.closeIntro()
		return m, nil
	case InitializeOKMsg:
		m.closeIntro()
		return m, nil
	case SwitchFocusMsg:
		m.setFocus(msg.Target)
		return m, nil
	case OpenModalMsg:
		m.openModal(msg.Kind, msg.Payload)
		return m, nil
	case CloseModalMsg:
		m.closeModal()
		return m, nil
	case ToastMsg:
		m.Toast = msg
		return m, nil
	case tea.KeyMsg:
		return m.updateKey(msg)
	default:
		return m, nil
	}
}

func (m Model) View() string {
	body := strings.Join([]string{
		m.renderTopBar(),
		m.renderChat(),
		m.renderInput(),
		m.renderStatusBar(),
	}, "\n")
	if m.Modals.Len() > 0 {
		return m.Modals.Render(body, m.Regions)
	}
	return body
}

func (m Model) updateKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	if m.Modals.Len() > 0 {
		switch msg.String() {
		case "ctrl+c", "ctrl+q":
			return m, tea.Quit
		case "esc":
			m.closeModal()
			return m, nil
		case "backspace":
			m.backspaceModal()
			return m, nil
		default:
			if msg.Type == tea.KeyRunes {
				m.Modals.UpdateTopInput(string(msg.Runes))
			}
			return m, nil
		}
	}
	switch msg.String() {
	case "ctrl+c", "ctrl+q":
		return m, tea.Quit
	case "ctrl+j":
		m.setFocus(FocusChat)
		return m, nil
	case "ctrl+i", "esc":
		m.setFocus(FocusInput)
		return m, nil
	case "pgup":
		if m.Focus.Target == FocusChat {
			m.ChatScrollAnchor = maxInt(0, m.ChatScrollAnchor-m.Regions.Chat.Height)
		}
		return m, nil
	case "pgdown":
		if m.Focus.Target == FocusChat {
			m.ChatScrollAnchor += maxInt(1, m.Regions.Chat.Height)
		}
		return m, nil
	case "home":
		if m.Focus.Target == FocusChat {
			m.ChatScrollAnchor = 0
		}
		return m, nil
	case "end":
		if m.Focus.Target == FocusChat {
			m.ChatScrollAnchor = 1 << 30
		}
		return m, nil
	case "backspace":
		m.backspaceInput()
		return m, nil
	}
	if msg.Type != tea.KeyRunes {
		return m, nil
	}
	text := string(msg.Runes)
	if text == "/" && strings.TrimSpace(m.Input) == "" && m.Focus.Target != FocusChat {
		m.openModal(ModalPalette, nil)
		return m, nil
	}
	if m.Focus.Target == FocusInput || m.Focus.Target == FocusIntro {
		m.Input += text
		m.closeIntro()
		m.relayout()
	}
	return m, nil
}

func (m *Model) resize(width, height int) {
	m.Width = maxInt(0, width)
	m.Height = maxInt(0, height)
	m.relayout()
}

func (m *Model) relayout() {
	m.Regions = ComputeRegions(m.Width, m.Height, m.inputRows())
}

func (m *Model) inputRows() int {
	lines := 1
	if m.Input != "" {
		lines = strings.Count(m.Input, "\n") + 1
	}
	return clampInt(lines+2, 3, 10)
}

func (m *Model) setFocus(target FocusTarget) {
	if target == FocusModal && m.Modals.Len() == 0 {
		target = FocusInput
	}
	m.Focus = m.Focus.WithTarget(target)
}

func (m *Model) openModal(kind ModalKind, payload any) {
	m.Modals.Push(Modal{Kind: kind, Payload: payload})
	m.setFocus(FocusModal)
}

func (m *Model) closeModal() {
	if _, ok := m.Modals.Pop(); ok && m.Modals.Len() == 0 {
		m.setFocus(FocusInput)
	}
}

func (m *Model) closeIntro() {
	if !m.Intro.Active {
		return
	}
	m.Intro.Active = false
	if m.Focus.Target == FocusIntro {
		m.setFocus(FocusInput)
	}
}

func (m *Model) backspaceInput() {
	if m.Input == "" || (m.Focus.Target != FocusInput && m.Focus.Target != FocusIntro) {
		return
	}
	runes := []rune(m.Input)
	m.Input = string(runes[:len(runes)-1])
	m.relayout()
}

func (m *Model) backspaceModal() {
	if m.Modals.Len() == 0 {
		return
	}
	top, ok := m.Modals.Pop()
	if !ok || top.Input == "" {
		if ok {
			m.Modals.Push(top)
		}
		return
	}
	runes := []rune(top.Input)
	top.Input = string(runes[:len(runes)-1])
	m.Modals.Push(top)
}

func (m Model) renderTopBar() string {
	return renderBlock(m.Regions.TopBar, "gocli-poor · repo:poor-cli · branch:main")
}

func (m Model) renderChat() string {
	if m.Intro.Active {
		return renderBlock(m.Regions.Chat, m.Intro.View())
	}
	return renderBlock(m.Regions.Chat, "chat transcript")
}

func (m Model) renderInput() string {
	value := m.Input
	if value == "" {
		value = "> "
	} else {
		value = "> " + value
	}
	return renderBlock(m.Regions.Input, value)
}

func (m Model) renderStatusBar() string {
	text := "ready"
	if m.Toast.Text != "" {
		text = m.Toast.Text
	}
	return renderBlock(m.Regions.StatusBar, text)
}

func renderBlock(rect Rect, text string) string {
	if rect.Height == 0 {
		return ""
	}
	lines := strings.Split(text, "\n")
	out := make([]string, rect.Height)
	for i := range out {
		line := ""
		if i < len(lines) {
			line = lines[i]
		}
		out[i] = fitLine(line, rect.Width)
	}
	return strings.Join(out, "\n")
}

func fitLine(line string, width int) string {
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
	return line + spaces(width-lipgloss.Width(line))
}

func introTimeoutCmd() tea.Cmd {
	return tea.Tick(500*time.Millisecond, func(time.Time) tea.Msg {
		return IntroDoneMsg{}
	})
}

type IntroModel struct {
	Active  bool
	Version string
}

func (m IntroModel) View() string {
	if m.Version == "" {
		m.Version = defaultIntroVersion
	}
	return "gocli-poor " + m.Version + " · connecting..."
}
