package widgets

import (
	"strings"

	"github.com/gongahkia/gocli-poor/internal/theme"
)

type Flush struct{}

// FlushHeader returns a single muted line to introduce a region, no border.
func FlushHeader(t *theme.Theme, label string) string {
	label = strings.TrimSpace(label)
	if t == nil {
		return label
	}
	return t.Muted.Render(label)
}

// FlushList renders a list without borders, one item per line with 2-space left pad.
func FlushList(t *theme.Theme, items []string, selectedIdx int) string {
	lines := make([]string, 0, len(items))
	for i, item := range items {
		prefix := "  "
		if i == selectedIdx {
			prefix = "› "
		}
		line := prefix + item
		if t != nil && i == selectedIdx {
			line = t.Focus.Render(line)
		}
		lines = append(lines, line)
	}
	return strings.Join(lines, "\n")
}
