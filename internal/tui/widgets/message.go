package widgets

import (
	"fmt"
	"strings"

	"github.com/mattn/go-runewidth"

	"github.com/gongahkia/gocli-poor/internal/markdown"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/tui/emptystate"
)

func renderMessage(msg state.Message, t *theme.Theme, md markdown.LineRenderer, width int, expanded map[string]bool, mp state.MultiplayerState) renderedMsg {
	width = maxInt(1, width)
	lines := make([]string, 0, 4)
	if len(msg.ToolCalls) > 0 {
		lines = append(lines, renderContent(msg, t, md, width, mp)...)
		for _, call := range msg.ToolCalls {
			lines = append(lines, renderToolBlock(call, expanded[toolKey(call)], width, t)...)
		}
	} else {
		lines = append(lines, renderContent(msg, t, md, width, mp)...)
	}
	if len(lines) == 0 {
		if msg.Role == state.RoleAssistant && msg.Streaming {
			lines = []string{emptystate.EmptyStateFor(emptystate.WaitingResponse).Render(t)}
		} else {
			lines = []string{rolePrefix(messageLabel(msg, mp), t)}
		}
	}
	if msg.Progress == "cancelled" {
		lines = append(lines, strings.Repeat(" ", runewidth.StringWidth(messageLabel(msg, mp))+1)+emptystate.EmptyStateFor(emptystate.Cancelled).Render(t))
	}
	return renderedMsg{id: msg.ID, raw: msg, blocks: lines, totalHeight: len(lines)}
}

func renderContent(msg state.Message, t *theme.Theme, md markdown.LineRenderer, width int, mp state.MultiplayerState) []string {
	if msg.Content == "" {
		return nil
	}
	label := messageLabel(msg, mp)
	prefix := rolePrefix(label, t) + " "
	prefixWidth := runewidth.StringWidth(label) + 1
	bodyWidth := maxInt(1, width-prefixWidth)
	body := renderBody(msg, md, bodyWidth)
	if len(body) == 0 {
		return []string{strings.TrimRight(prefix, " ")}
	}
	lines := make([]string, 0, len(body))
	lines = append(lines, prefix+body[0])
	indent := strings.Repeat(" ", prefixWidth)
	for _, line := range body[1:] {
		lines = append(lines, indent+line)
	}
	return lines
}

func renderBody(msg state.Message, md markdown.LineRenderer, width int) []string {
	if msg.Role == state.RoleAssistant && len(msg.Segments) > 0 {
		lines := make([]string, 0, len(msg.Segments))
		for _, seg := range msg.Segments {
			if seg.Text == "" && seg.Plain == "" {
				lines = append(lines, "")
				continue
			}
			if seg.Text != "" {
				lines = append(lines, strings.TrimSuffix(seg.Text, "\n"))
			} else {
				lines = append(lines, strings.TrimSuffix(seg.Plain, "\n"))
			}
		}
		return lines
	}
	if msg.Role == state.RoleAssistant && md != nil {
		segs := md.Render(msg.Content, width)
		lines := make([]string, 0, len(segs))
		for _, seg := range segs {
			if seg.Text == "" && seg.Plain == "" {
				lines = append(lines, "")
				continue
			}
			if seg.Text != "" {
				lines = append(lines, seg.Text)
			} else {
				lines = append(lines, seg.Plain)
			}
		}
		return lines
	}
	return wrapPlain(msg.Content, width)
}

func rolePrefix(label string, t *theme.Theme) string {
	if t == nil {
		return label
	}
	return t.Muted.Render(label)
}

func messageLabel(msg state.Message, mp state.MultiplayerState) string {
	if mp.Enabled {
		authorID := strings.TrimSpace(msg.AuthorConnectionID)
		localID := strings.TrimSpace(mp.LocalConnectionID)
		if localID == "" {
			localID = "local"
		}
		remote := authorID != "" && authorID != "local" && authorID != localID
		name := cleanAuthorName(msg.AuthorDisplayName)
		if name == "" {
			name = authorID
		}
		if remote && name != "" {
			if msg.Role == state.RoleAssistant {
				return "poor-cli · replying to " + name
			}
			return name + " ›"
		}
	}
	switch msg.Role {
	case state.RoleUser:
		return "you ›"
	case state.RoleAssistant:
		return "poor-cli ›"
	case state.RoleTool:
		return "tool"
	case state.RoleSystem:
		return "system"
	default:
		if msg.Role == "" {
			return "msg"
		}
		return string(msg.Role)
	}
}

func cleanAuthorName(name string) string {
	name = strings.ReplaceAll(name, "\n", " ")
	name = strings.ReplaceAll(name, "\r", " ")
	return strings.Join(strings.Fields(name), " ")
}

func wrapPlain(text string, width int) []string {
	width = maxInt(1, width)
	if text == "" {
		return nil
	}
	raw := strings.Split(strings.ReplaceAll(text, "\t", "    "), "\n")
	out := make([]string, 0, len(raw))
	for _, line := range raw {
		out = append(out, wrapPlainLine(line, width)...)
	}
	return out
}

func wrapPlainLine(line string, width int) []string {
	if line == "" {
		return []string{""}
	}
	var out []string
	var b strings.Builder
	col := 0
	for _, r := range line {
		w := runewidth.RuneWidth(r)
		if col > 0 && col+w > width {
			out = append(out, b.String())
			b.Reset()
			col = 0
		}
		b.WriteRune(r)
		col += w
	}
	out = append(out, b.String())
	return out
}

func truncateWidth(text string, width int) string {
	width = maxInt(1, width)
	if runewidth.StringWidth(text) <= width {
		return text
	}
	var b strings.Builder
	col := 0
	for _, r := range text {
		w := runewidth.RuneWidth(r)
		if col+w > width-1 {
			break
		}
		b.WriteRune(r)
		col += w
	}
	return fmt.Sprintf("%s.", b.String())
}
