package markdown

import (
	"strings"
	"sync"

	"github.com/alecthomas/chroma/v2"
	"github.com/alecthomas/chroma/v2/lexers"
	"github.com/alecthomas/chroma/v2/styles"
	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/theme"
)

type Highlighter struct {
	theme  *theme.Theme
	style  *chroma.Style
	lexers map[string]chroma.Lexer
	styles map[chroma.TokenType]lipgloss.Style
	mu     sync.RWMutex
}

var langAliases = map[string]string{
	"golang": "go",
	"py":     "python",
	"ts":     "typescript",
	"sh":     "bash",
	"rs":     "rust",
}

func NewHighlighter(t *theme.Theme) *Highlighter {
	if t == nil {
		defaultTheme := theme.DarkWithCapability(theme.CapabilityTrueColor)
		t = &defaultTheme
	}
	return &Highlighter{
		theme:  t,
		style:  styles.Get(chromaStyleName(t)),
		lexers: make(map[string]chroma.Lexer),
		styles: make(map[chroma.TokenType]lipgloss.Style),
	}
}

func (h *Highlighter) HighlightLine(lang, line string) string {
	if h.theme != nil && h.theme.Capability == theme.CapabilityMonochrome {
		return line
	}
	lexer := h.lexer(lang)
	if lexer == nil {
		return line
	}
	return h.highlight(lexer, line)
}

func (h *Highlighter) HighlightBlock(lang, code string) string {
	if h.theme != nil && h.theme.Capability == theme.CapabilityMonochrome {
		return code
	}
	lexer := h.lexer(lang)
	if lexer == nil {
		return code
	}
	return h.highlight(lexer, code)
}

func chromaStyleName(t *theme.Theme) string {
	if strings.Contains(strings.ToLower(t.Name), "light") {
		return "friendly"
	}
	return "monokai"
}

func (h *Highlighter) lexer(lang string) chroma.Lexer {
	key := normalizeLang(lang)
	if key == "" {
		return nil
	}
	h.mu.RLock()
	lexer, ok := h.lexers[key]
	h.mu.RUnlock()
	if ok {
		return lexer
	}
	lexer = lexers.Get(key)
	if lexer == nil {
		if alias, ok := langAliases[key]; ok {
			lexer = lexers.Get(alias)
		}
	}
	if lexer != nil {
		lexer = chroma.Coalesce(lexer)
	}
	h.mu.Lock()
	h.lexers[key] = lexer
	h.mu.Unlock()
	return lexer
}

func normalizeLang(lang string) string {
	fields := strings.Fields(strings.TrimSpace(strings.ToLower(lang)))
	if len(fields) == 0 {
		return ""
	}
	return fields[0]
}

func (h *Highlighter) highlight(lexer chroma.Lexer, code string) string {
	it, err := lexer.Tokenise(nil, code)
	if err != nil {
		return code
	}
	var b strings.Builder
	for token := it(); token != chroma.EOF; token = it() {
		if token.Value == "" {
			continue
		}
		b.WriteString(h.tokenStyle(token.Type).Render(token.Value))
	}
	return b.String()
}

func (h *Highlighter) tokenStyle(tt chroma.TokenType) lipgloss.Style {
	h.mu.RLock()
	style, ok := h.styles[tt]
	h.mu.RUnlock()
	if ok {
		return style
	}
	style = h.theme.Base
	if h.style != nil {
		entry := h.style.Get(tt)
		style = h.tokenBaseStyle(tt)
		style = style.
			Bold(entry.Bold == chroma.Yes).
			Italic(entry.Italic == chroma.Yes).
			Underline(entry.Underline == chroma.Yes)
	}
	h.mu.Lock()
	h.styles[tt] = style
	h.mu.Unlock()
	return style
}

func (h *Highlighter) tokenBaseStyle(tt chroma.TokenType) lipgloss.Style {
	name := tt.String()
	switch {
	case strings.HasPrefix(name, "Keyword"), strings.HasPrefix(name, "NameFunction"), strings.HasPrefix(name, "NameClass"):
		return h.theme.Focus
	case strings.Contains(name, "String"):
		return h.theme.Success
	case strings.Contains(name, "Number"):
		return h.theme.Warning
	case strings.HasPrefix(name, "Comment"):
		return h.theme.Muted
	case strings.HasPrefix(name, "Error"):
		return h.theme.Error
	default:
		return h.theme.Base
	}
}
