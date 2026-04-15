package widgets

import (
	"fmt"
	"strings"

	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
)

func renderToolBlock(call state.ToolCall, expanded bool, width int, t *theme.Theme) []string {
	width = maxInt(1, width)
	head := "▸"
	if expanded {
		head = "▾"
	}
	header := truncateWidth(fmt.Sprintf("%s %s", head, toolHeader(call)), width)
	lines := []string{muted(header, t)}
	if !expanded {
		if preview := firstLine(call.ArgsPreview); preview != "" {
			lines = append(lines, muted("  └─ "+truncateWidth(preview, maxInt(1, width-5)), t))
		}
		return lines
	}
	if call.ArgsPreview != "" {
		for i, line := range wrapPlain(call.ArgsPreview, maxInt(1, width-8)) {
			prefix := "  args: "
			if i > 0 {
				prefix = "        "
			}
			lines = append(lines, muted(prefix+line, t))
		}
	}
	output := toolOutput(call)
	if output != "" {
		lines = append(lines, muted("  output:", t))
		for _, line := range wrapPlain(output, maxInt(1, width-4)) {
			lines = append(lines, muted("    "+line, t))
		}
	}
	return lines
}

func toolHeader(call state.ToolCall) string {
	name := call.ToolName
	if name == "" {
		name = "tool"
	}
	status := call.Status
	if status == "" {
		status = "pending"
	}
	return fmt.Sprintf("%s · %s", name, status)
}

func toolOutput(call state.ToolCall) string {
	if call.Error != "" {
		return call.Error
	}
	if call.ResultPreview != "" {
		return call.ResultPreview
	}
	return strings.Join(call.Chunks, "")
}

func firstLine(s string) string {
	s = strings.TrimSpace(s)
	if s == "" {
		return ""
	}
	if i := strings.IndexByte(s, '\n'); i >= 0 {
		return s[:i]
	}
	return s
}

func toolKey(call state.ToolCall) string {
	switch {
	case call.EventID != "":
		return call.EventID
	case call.ToolCallID != "":
		return call.ToolCallID
	case call.TurnID != "" || call.ToolName != "":
		return call.TurnID + ":" + call.ToolName
	default:
		return "tool"
	}
}

func muted(s string, t *theme.Theme) string {
	if t == nil {
		return s
	}
	return t.Muted.Render(s)
}
