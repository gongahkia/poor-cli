package widgets

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
)

const UsersPanelWidth = 28

type UsersPanel struct {
	theme    *theme.Theme
	members  []state.Member
	typing   map[string]bool
	selected int
	offset   int
}

func NewUsersPanel(t *theme.Theme) *UsersPanel {
	return &UsersPanel{theme: t}
}

func (p *UsersPanel) SetState(st state.MultiplayerState) {
	p.members = append([]state.Member(nil), st.Members...)
	p.typing = map[string]bool{}
	for k, v := range st.Typing {
		p.typing[k] = v
	}
	if p.selected >= len(p.members) {
		p.selected = len(p.members) - 1
	}
	if p.selected < 0 {
		p.selected = 0
	}
}

func (p *UsersPanel) Update(msg tea.KeyMsg, height int) {
	switch msg.String() {
	case "up", "k":
		if p.selected > 0 {
			p.selected--
		}
	case "down", "j":
		if p.selected < len(p.members)-1 {
			p.selected++
		}
	}
	p.clamp(height)
}

func (p *UsersPanel) CurrentMember() (state.Member, bool) {
	if p == nil || p.selected < 0 || p.selected >= len(p.members) {
		return state.Member{}, false
	}
	return p.members[p.selected], true
}

func (p *UsersPanel) View(width, height int) string {
	if width <= 0 || height <= 0 {
		return ""
	}
	width = usersMin(width, UsersPanelWidth)
	p.clamp(height)
	rows := []string{p.fit(p.header(), width)}
	memberRows := usersMax(0, height-1)
	start := p.offset
	end := usersMin(len(p.members), start+(memberRows+1)/2)
	for i := start; i < end; i++ {
		top, bottom := p.memberLines(i, width)
		rows = append(rows, top, bottom)
	}
	if len(rows) > height {
		rows = rows[:height]
	}
	for len(rows) < height {
		rows = append(rows, p.fit("", width))
	}
	return strings.Join(rows, "\n")
}

func (p *UsersPanel) header() string {
	return fmt.Sprintf("users · %d", len(p.members))
}

func (p *UsersPanel) memberLines(index, width int) (string, string) {
	member := p.members[index]
	name := truncateDisplay(firstNonEmpty(member.DisplayName, member.ConnectionID, "?"), 16)
	role := firstNonEmpty(member.Role, "viewer")
	marker := " "
	if index == p.selected {
		marker = ">"
	}
	status := p.status(member)
	nameWidth := usersMax(1, width-1-1-lipgloss.Width(role))
	top := marker + padDisplay(name, nameWidth) + " " + p.muted(role)
	bottom := "  " + p.statusStyle(member, status)
	return p.fit(top, width), p.fit(bottom, width)
}

func (p *UsersPanel) status(member state.Member) string {
	if p.typing != nil && p.typing[member.ConnectionID] {
		return "● typing"
	}
	if member.QueuePosition > 0 {
		return fmt.Sprintf("#%d queue", member.QueuePosition)
	}
	if member.VotesPending > 0 {
		return fmt.Sprintf("voted %d/%d", member.VotesCast, member.VotesPending)
	}
	if member.ApprovalState == "pending" {
		return "pending"
	}
	if member.HandRaised {
		return "hand raised"
	}
	return ""
}

func (p *UsersPanel) statusStyle(member state.Member, status string) string {
	if status == "" {
		return ""
	}
	if status == "pending" {
		return p.warning(status)
	}
	if status == "● typing" {
		return p.focus(status)
	}
	return p.muted(status)
}

func (p *UsersPanel) clamp(height int) {
	if len(p.members) == 0 {
		p.selected = 0
		p.offset = 0
		return
	}
	visible := usersMax(1, (usersMax(1, height)-1)/2)
	if p.selected < p.offset {
		p.offset = p.selected
	}
	if p.selected >= p.offset+visible {
		p.offset = p.selected - visible + 1
	}
	maxOffset := usersMax(0, len(p.members)-visible)
	if p.offset > maxOffset {
		p.offset = maxOffset
	}
	if p.offset < 0 {
		p.offset = 0
	}
}

func (p *UsersPanel) fit(line string, width int) string {
	fitted := fitDisplay(line, width)
	return fitted + strings.Repeat(" ", usersMax(0, width-lipgloss.Width(fitted)))
}

func (p *UsersPanel) muted(text string) string {
	if p.theme == nil {
		return text
	}
	return p.theme.Muted.Render(text)
}

func (p *UsersPanel) focus(text string) string {
	if p.theme == nil {
		return text
	}
	return p.theme.Focus.Render(text)
}

func (p *UsersPanel) warning(text string) string {
	if p.theme == nil {
		return text
	}
	return p.theme.Warning.Render(text)
}

func truncateDisplay(text string, width int) string {
	return fitDisplay(text, width)
}

func fitDisplay(text string, width int) string {
	if width <= 0 {
		return ""
	}
	if lipgloss.Width(text) <= width {
		return text
	}
	runes := []rune(text)
	for len(runes) > 0 && lipgloss.Width(string(runes)) > width {
		runes = runes[:len(runes)-1]
	}
	return string(runes)
}

func padDisplay(text string, width int) string {
	fitted := fitDisplay(text, width)
	return fitted + strings.Repeat(" ", usersMax(0, width-lipgloss.Width(fitted)))
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func usersMin(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func usersMax(a, b int) int {
	if a > b {
		return a
	}
	return b
}
