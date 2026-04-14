package tui

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

type Modal struct {
	Kind    ModalKind
	Payload any
	Input   string
}

type ModalStack []Modal

func (s *ModalStack) Push(modal Modal) {
	*s = append(*s, modal)
}

func (s *ModalStack) Pop() (Modal, bool) {
	if len(*s) == 0 {
		return Modal{}, false
	}
	last := (*s)[len(*s)-1]
	*s = (*s)[:len(*s)-1]
	return last, true
}

func (s ModalStack) Top() (Modal, bool) {
	if len(s) == 0 {
		return Modal{}, false
	}
	return s[len(s)-1], true
}

func (s ModalStack) Len() int {
	return len(s)
}

func (s *ModalStack) UpdateTopInput(msg string) {
	if len(*s) == 0 {
		return
	}
	top := &(*s)[len(*s)-1]
	top.Input += msg
}

func (s ModalStack) Render(base string, regions Regions) string {
	out := base
	for _, modal := range s {
		out = overlay(out, modal.Render(regions.Modal.Width, regions.Modal.Height), regions.Modal)
	}
	return out
}

func (m Modal) Render(width, height int) string {
	width = maxInt(1, width)
	height = maxInt(1, height)
	bodyHeight := maxInt(1, height-2)
	title := modalTitle(m.Kind)
	body := modalBody(m)
	box := lipgloss.NewStyle().
		Width(width).
		Height(height).
		Border(lipgloss.NormalBorder()).
		Render(title + "\n" + lipgloss.Place(width-2, bodyHeight, lipgloss.Left, lipgloss.Top, body))
	return box
}

func modalTitle(kind ModalKind) string {
	switch kind {
	case ModalPalette:
		return "command palette"
	case ModalMention:
		return "mention"
	case ModalProviderPicker:
		return "provider"
	case ModalPermissionPrompt:
		return "permission"
	default:
		return "modal"
	}
}

func modalBody(m Modal) string {
	if text, ok := m.Payload.(string); ok && text != "" {
		if m.Input != "" {
			return text + "\n" + m.Input
		}
		return text
	}
	if m.Input != "" {
		return m.Input
	}
	return "type to filter"
}

func overlay(base, cover string, rect Rect) string {
	baseLines := strings.Split(base, "\n")
	coverLines := strings.Split(cover, "\n")
	for len(baseLines) < rect.Y+len(coverLines) {
		baseLines = append(baseLines, "")
	}
	for y, line := range coverLines {
		target := rect.Y + y
		baseLines[target] = replaceAt(baseLines[target], line, rect.X)
	}
	return strings.Join(baseLines, "\n")
}

func replaceAt(dst, src string, x int) string {
	if x <= 0 {
		if lipgloss.Width(dst) <= lipgloss.Width(src) {
			return src
		}
		return src + spaces(lipgloss.Width(dst)-lipgloss.Width(src))
	}
	dstWidth := lipgloss.Width(dst)
	if dstWidth < x {
		dst += spaces(x - dstWidth)
	}
	left := []rune(dst)
	if len(left) > x {
		left = left[:x]
	}
	rightStart := x + lipgloss.Width(src)
	right := ""
	if dstWidth > rightStart {
		rightRunes := []rune(dst)
		if len(rightRunes) > rightStart {
			right = string(rightRunes[rightStart:])
		}
	}
	return string(left) + src + right
}

func spaces(n int) string {
	if n <= 0 {
		return ""
	}
	return strings.Repeat(" ", n)
}
