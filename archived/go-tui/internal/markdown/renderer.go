package markdown

import (
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"

	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/mattn/go-runewidth"
)

const (
	maxSegments     = 10000
	maxSegmentChars = 4096
)

type Segment struct {
	Text  string
	Plain string
	Width int
}

type Mark uint64

type LineRenderer interface {
	Render(text string, width int) []Segment
}

type PlainRenderer struct{}

func NewPlainRenderer() PlainRenderer {
	return PlainRenderer{}
}

func (PlainRenderer) Render(text string, width int) []Segment {
	width = mdMaxInt(1, width)
	lines := wrapPlain(text, width)
	out := make([]Segment, 0, len(lines))
	for _, line := range lines {
		out = append(out, Segment{Text: line, Plain: line, Width: runewidth.StringWidth(line)})
	}
	return out
}

type Renderer struct {
	theme    *theme.Theme
	hl       *Highlighter
	width    int
	events   []Event
	segments []Segment
	commits  []commitMark
	nextMark Mark

	open        []BlockKind
	codeLang    string
	codePending bool
	codeStart   int
	blockLines  []string
	listKind    BlockKind
	listNumber  int
	itemPrefix  string
}

type RendererDeps struct {
	Theme       *theme.Theme
	Highlighter *Highlighter
	Width       int
}

type commitMark struct {
	mark Mark
	end  int
}

type styledRun struct {
	plain string
	style lipgloss.Style
}

type renderCell struct {
	text  string
	width int
	style int
}

func NewRenderer(t *theme.Theme, highlighter *Highlighter, width int) *Renderer {
	if t == nil {
		defaultTheme := theme.DarkWithCapability(theme.CapabilityMonochrome)
		t = &defaultTheme
	}
	if highlighter == nil {
		highlighter = NewHighlighter(t)
	}
	r := &Renderer{theme: t, hl: highlighter, width: width}
	r.resetRenderState()
	return r
}

func NewRendererWithDeps(d RendererDeps) *Renderer {
	return NewRenderer(d.Theme, d.Highlighter, d.Width)
}

func (r *Renderer) Feed(events []Event) {
	if len(events) == 0 {
		return
	}
	r.events = append(r.events, events...)
	r.renderEvents(events)
}

func (r *Renderer) Full() string {
	var b strings.Builder
	for _, seg := range r.segments {
		b.WriteString(seg.Text)
	}
	return b.String()
}

func (r *Renderer) TailSince(mark Mark) (string, Mark) {
	if len(r.commits) == 0 {
		return "", mark
	}
	start := 0
	for _, commit := range r.commits {
		if commit.mark == mark {
			start = commit.end
			break
		}
		if commit.mark < mark {
			start = commit.end
		}
	}
	latest := r.commits[len(r.commits)-1].mark
	var b strings.Builder
	for _, seg := range r.segments[start:] {
		b.WriteString(seg.Text)
	}
	return b.String(), latest
}

func (r *Renderer) Resize(width int) {
	if width == r.width {
		return
	}
	r.width = width
	events := append([]Event(nil), r.events...)
	r.segments = nil
	r.commits = nil
	r.nextMark = 0
	r.resetRenderState()
	r.renderEvents(events)
}

func (r *Renderer) Mark() Mark {
	if len(r.commits) == 0 {
		return 0
	}
	return r.commits[len(r.commits)-1].mark
}

func (r *Renderer) Render(text string, width int) []Segment {
	streamer := NewStreamer(r.theme, r.hl, width)
	streamer.Write([]byte(text))
	streamer.Close()
	full := streamer.Full()
	full = strings.TrimSuffix(full, "\n")
	if full == "" {
		return nil
	}
	lines := strings.Split(full, "\n")
	out := make([]Segment, 0, len(lines))
	for _, line := range lines {
		plain := stripANSI(line)
		out = append(out, Segment{Text: line, Plain: plain, Width: runewidth.StringWidth(plain)})
	}
	return out
}

func (r *Renderer) resetRenderState() {
	r.open = nil
	r.codeLang = ""
	r.codePending = false
	r.codeStart = 0
	r.blockLines = nil
	r.listKind = 0
	r.listNumber = 1
	r.itemPrefix = ""
}

func (r *Renderer) renderEvents(events []Event) {
	for _, event := range events {
		switch e := event.(type) {
		case BlockOpenEvent:
			r.openBlock(eventBlock(e.Kind, e.Block), e.Info)
		case BlockCloseEvent:
			r.closeBlock(eventBlock(e.Kind, e.Block))
		case RawLineEvent:
			r.rawLine(eventBlock(e.Kind, e.Block), e.Text)
		case CodeBlockDeltaEvent:
			r.renderCodeDelta(e)
		case CommitEvent:
			r.commit(e.Mark)
		}
	}
}

func (r *Renderer) openBlock(kind BlockKind, info string) {
	r.open = append(r.open, kind)
	switch kind {
	case BlockCodeFence:
		r.codePending = false
		r.codeStart = 0
		r.codeLang = normalizeLang(info)
		r.addCodeBorder(true)
	case BlockParagraph, BlockBlockquote, BlockListItem:
		r.blockLines = nil
	case BlockHeading1, BlockHeading2, BlockHeading3, BlockHeading4, BlockHeading5, BlockHeading6:
		r.blockLines = nil
	case BlockListUnordered:
		r.listKind = kind
	case BlockListOrdered:
		r.listKind = kind
		if n, err := strconv.Atoi(strings.TrimSpace(info)); err == nil && n > 0 {
			r.listNumber = n
		} else {
			r.listNumber = 1
		}
	case BlockThematicBreak:
		r.blockLines = nil
	}
	if kind == BlockListItem {
		if r.listKind == BlockListOrdered {
			r.itemPrefix = strconv.Itoa(r.listNumber) + ". "
			r.listNumber++
		} else {
			r.itemPrefix = "• "
		}
	}
}

func (r *Renderer) closeBlock(kind BlockKind) {
	switch kind {
	case BlockParagraph:
		r.renderParagraph()
	case BlockHeading1, BlockHeading2, BlockHeading3, BlockHeading4, BlockHeading5, BlockHeading6:
		r.renderHeading(kind)
	case BlockCodeFence:
		r.codePending = false
		r.codeStart = 0
		r.addCodeBorder(false)
		r.codeLang = ""
	case BlockBlockquote:
		r.renderBlockquote()
	case BlockListItem:
		r.renderListItem()
		r.itemPrefix = ""
	case BlockListUnordered, BlockListOrdered:
		r.listKind = 0
		r.listNumber = 1
	case BlockThematicBreak:
		r.renderThematicBreak()
	}
	r.blockLines = nil
	if len(r.open) > 0 {
		r.open = r.open[:len(r.open)-1]
	}
}

func (r *Renderer) rawLine(kind BlockKind, text string) {
	if kind == BlockCodeFence || r.currentBlock() == BlockCodeFence {
		r.renderCodeLine(r.codeLang, text)
		return
	}
	r.blockLines = append(r.blockLines, text)
}

func (r *Renderer) commit(raw uint64) {
	mark := Mark(raw)
	if mark == 0 {
		r.nextMark++
		mark = r.nextMark
	} else if mark > r.nextMark {
		r.nextMark = mark
	}
	r.commits = append(r.commits, commitMark{mark: mark, end: len(r.segments)})
}

func (r *Renderer) currentBlock() BlockKind {
	if len(r.open) == 0 {
		return BlockParagraph
	}
	return r.open[len(r.open)-1]
}

func (r *Renderer) renderParagraph() {
	text := strings.Join(trimNonEmpty(r.blockLines), " ")
	if text == "" {
		return
	}
	r.renderInlineText(text, r.theme.Base, "", "", r.theme.Base)
}

func (r *Renderer) renderHeading(kind BlockKind) {
	text := strings.Join(trimNonEmpty(r.blockLines), " ")
	if text == "" {
		return
	}
	r.renderInlineText(text, r.headingStyle(kind), "", "", r.headingStyle(kind))
	r.addLine("", "", 0)
}

func (r *Renderer) renderBlockquote() {
	for _, line := range r.blockLines {
		if strings.TrimSpace(line) == "" {
			r.addLine(r.theme.Muted.Render("│ "), "│ ", runewidth.StringWidth("│ "))
			continue
		}
		r.renderInlineText(line, r.theme.Muted, "│ ", "│ ", r.theme.Muted)
	}
}

func (r *Renderer) renderListItem() {
	text := strings.Join(trimNonEmpty(r.blockLines), " ")
	if text == "" {
		text = " "
	}
	cont := strings.Repeat(" ", runewidth.StringWidth(r.itemPrefix))
	r.renderInlineText(text, r.theme.Base, r.itemPrefix, cont, r.theme.Muted)
}

func (r *Renderer) renderThematicBreak() {
	width := r.wrapWidth()
	line := strings.Repeat("─", width)
	r.addLine(r.theme.Muted.Render(line), line, width)
}

func (r *Renderer) renderCodeLine(lang, line string) {
	lang = normalizeLang(lang)
	if lang == "" {
		lang = r.codeLang
	}
	prefix := "│ "
	prefixWidth := runewidth.StringWidth(prefix)
	width := mdMaxInt(1, r.wrapWidth()-prefixWidth)
	for _, chunk := range wrapLineCap(strings.ReplaceAll(line, "\t", "    "), width) {
		highlighted := chunk
		if r.hl != nil {
			highlighted = r.hl.HighlightLine(lang, chunk)
		}
		styledPrefix := r.theme.Muted.Render(prefix)
		r.addLine(styledPrefix+highlighted, prefix+chunk, prefixWidth+runewidth.StringWidth(chunk))
	}
}

func (r *Renderer) renderCodeDelta(e CodeBlockDeltaEvent) {
	if r.codePending {
		r.segments = r.segments[:r.codeStart]
	} else {
		r.codeStart = len(r.segments)
	}
	r.renderCodeLine(e.Lang, e.Line)
	r.codePending = !e.Final
	if e.Final {
		r.codeStart = 0
	}
}

func (r *Renderer) addCodeBorder(open bool) {
	width := r.wrapWidth()
	var line string
	if open {
		if r.codeLang != "" {
			head := "╭─ " + r.codeLang + " "
			line = head + strings.Repeat("─", mdMaxInt(0, width-runewidth.StringWidth(head)))
		} else {
			line = "╭" + strings.Repeat("─", mdMaxInt(0, width-1))
		}
	} else {
		line = "╰" + strings.Repeat("─", mdMaxInt(0, width-1))
	}
	r.addLine(r.theme.Muted.Render(line), line, runewidth.StringWidth(line))
}

func (r *Renderer) renderInlineText(text string, base lipgloss.Style, firstPrefix, nextPrefix string, prefixStyle lipgloss.Style) {
	width := r.wrapWidth()
	firstWidth := runewidth.StringWidth(firstPrefix)
	nextWidth := runewidth.StringWidth(nextPrefix)
	if r.theme.Capability == theme.CapabilityMonochrome {
		if isPlainASCIIInline(text) {
			r.renderPlainASCIIInline(text, width, firstPrefix, nextPrefix, firstWidth, nextWidth)
			return
		}
		if isASCIIInlineCandidate(text) {
			r.renderPlainASCIIInline(plainInlineText(text), width, firstPrefix, nextPrefix, firstWidth, nextWidth)
			return
		}
	}
	runs := inlineRuns(text, base, r.theme)
	cells, styles := cellsFromRuns(runs)
	lines := wrapCells(cells, mdMaxInt(1, width-firstWidth))
	for i, line := range lines {
		prefix := firstPrefix
		prefixWidth := firstWidth
		if i > 0 {
			prefix = nextPrefix
			prefixWidth = nextWidth
		}
		if i > 0 && firstWidth != nextWidth {
			line = rewrapLine(line, mdMaxInt(1, width-prefixWidth))
		}
		styled, plain := renderCells(line, styles)
		r.addLine(prefixStyle.Render(prefix)+styled, prefix+plain, prefixWidth+runewidth.StringWidth(plain))
	}
}

func (r *Renderer) renderPlainASCIIInline(text string, width int, firstPrefix, nextPrefix string, firstWidth, nextWidth int) {
	prefix := firstPrefix
	prefixWidth := firstWidth
	for len(text) > 0 {
		lineWidth := mdMaxInt(1, width-prefixWidth)
		line := text
		if len(line) > lineWidth {
			cut := strings.LastIndexByte(line[:lineWidth+1], ' ')
			if cut <= 0 {
				cut = lineWidth
			}
			line = strings.TrimRight(text[:cut], " ")
			text = strings.TrimLeft(text[cut:], " ")
		} else {
			text = ""
		}
		out := prefix + line
		r.addLine(out, out, prefixWidth+len(line))
		prefix = nextPrefix
		prefixWidth = nextWidth
	}
}

func isPlainASCIIInline(text string) bool {
	for i := 0; i < len(text); i++ {
		switch c := text[i]; {
		case c >= utf8.RuneSelf:
			return false
		case c == '*' || c == '_' || c == '`' || c == '[' || c == '<' || c == '\t':
			return false
		}
	}
	return true
}

func isASCIIInlineCandidate(text string) bool {
	for i := 0; i < len(text); i++ {
		if text[i] >= utf8.RuneSelf || text[i] == '\t' {
			return false
		}
	}
	return true
}

func plainInlineText(text string) string {
	events := NewInlineTokenizer().FeedLine(RawLineEvent{Text: text})
	var b strings.Builder
	for _, event := range events {
		switch e := event.(type) {
		case TextEvent:
			b.WriteString(e.Value)
		case LinkEvent:
			b.WriteString(e.Text)
		}
	}
	return b.String()
}

func inlineRuns(text string, base lipgloss.Style, t *theme.Theme) []styledRun {
	events := NewInlineTokenizer().FeedLine(RawLineEvent{Text: text})
	state := inlineState{}
	out := make([]styledRun, 0, len(events))
	for _, event := range events {
		switch e := event.(type) {
		case InlineOpenEvent:
			state.open(e.Kind)
		case InlineCloseEvent:
			state.close(e.Kind)
		case TextEvent:
			out = append(out, styledRun{plain: e.Value, style: state.style(base, t)})
		case LinkEvent:
			out = append(out, styledRun{plain: e.Text, style: t.ChatLink})
		}
	}
	if len(out) == 0 {
		return []styledRun{{plain: text, style: base}}
	}
	return out
}

type inlineState struct {
	emphasis bool
	strong   bool
	code     bool
}

func (s *inlineState) open(kind InlineKind) {
	switch kind {
	case InlineEmphasis:
		s.emphasis = true
	case InlineStrong:
		s.strong = true
	case InlineCode:
		s.code = true
	}
}

func (s *inlineState) close(kind InlineKind) {
	switch kind {
	case InlineEmphasis:
		s.emphasis = false
	case InlineStrong:
		s.strong = false
	case InlineCode:
		s.code = false
	}
}

func (s inlineState) style(base lipgloss.Style, t *theme.Theme) lipgloss.Style {
	style := base
	if s.code {
		style = t.ChatCode
	}
	if s.strong {
		style = style.Bold(true)
	}
	if s.emphasis {
		style = style.Italic(true)
	}
	return style
}

func cellsFromRuns(runs []styledRun) ([]renderCell, []lipgloss.Style) {
	styles := make([]lipgloss.Style, 0, len(runs))
	cells := make([]renderCell, 0)
	for _, run := range runs {
		styleID := len(styles)
		styles = append(styles, run.style)
		text := strings.ReplaceAll(run.plain, "\t", "    ")
		for len(text) > 0 {
			r, size := utf8.DecodeRuneInString(text)
			if r == utf8.RuneError && size == 0 {
				break
			}
			raw := text[:size]
			text = text[size:]
			cells = append(cells, renderCell{text: raw, width: runewidth.RuneWidth(r), style: styleID})
		}
	}
	return cells, styles
}

func wrapCells(cells []renderCell, width int) [][]renderCell {
	width = mdMaxInt(1, mdMinInt(width, maxSegmentChars))
	if len(cells) == 0 {
		return [][]renderCell{{}}
	}
	var lines [][]renderCell
	var line []renderCell
	col := 0
	for p := 0; p < len(cells); {
		q := p
		space := isSpaceCell(cells[p])
		for q < len(cells) && isSpaceCell(cells[q]) == space {
			q++
		}
		token := cells[p:q]
		tokenWidth := cellsWidth(token)
		switch {
		case space && col == 0:
		case space && col+tokenWidth > width:
			lines = append(lines, line)
			line = nil
			col = 0
		case !space && tokenWidth > width:
			for _, cell := range token {
				if col > 0 && col+cell.width > width {
					lines = append(lines, line)
					line = nil
					col = 0
				}
				line = append(line, cell)
				col += cell.width
			}
		case !space && col > 0 && col+tokenWidth > width:
			lines = append(lines, line)
			line = append([]renderCell(nil), token...)
			col = tokenWidth
		default:
			line = append(line, token...)
			col += tokenWidth
		}
		p = q
	}
	lines = append(lines, line)
	return lines
}

func rewrapLine(cells []renderCell, width int) []renderCell {
	lines := wrapCells(cells, width)
	if len(lines) == 0 {
		return nil
	}
	return lines[0]
}

func renderCells(cells []renderCell, styles []lipgloss.Style) (string, string) {
	var styled strings.Builder
	var plain strings.Builder
	for p := 0; p < len(cells); {
		q := p + 1
		for q < len(cells) && cells[q].style == cells[p].style {
			q++
		}
		var chunk strings.Builder
		for _, cell := range cells[p:q] {
			chunk.WriteString(cell.text)
		}
		s := chunk.String()
		plain.WriteString(s)
		if cells[p].style >= 0 && cells[p].style < len(styles) {
			styled.WriteString(styles[cells[p].style].Render(s))
		} else {
			styled.WriteString(s)
		}
		p = q
	}
	return styled.String(), plain.String()
}

func cellsWidth(cells []renderCell) int {
	width := 0
	for _, cell := range cells {
		width += cell.width
	}
	return width
}

func isSpaceCell(cell renderCell) bool {
	r, _ := utf8.DecodeRuneInString(cell.text)
	return unicode.IsSpace(r)
}

func (r *Renderer) headingStyle(kind BlockKind) lipgloss.Style {
	switch kind {
	case BlockHeading1:
		return r.theme.Focus.Bold(true)
	case BlockHeading2, BlockHeading3:
		return r.theme.Info.Bold(true)
	default:
		return r.theme.Base.Bold(true)
	}
}

func (r *Renderer) addLine(styled, plain string, width int) {
	if styled == plain {
		line := styled + "\n"
		r.addSegment(Segment{Text: line, Plain: line, Width: width})
		return
	}
	r.addSegment(Segment{Text: styled + "\n", Plain: plain + "\n", Width: width})
}

func (r *Renderer) addSegment(seg Segment) {
	r.segments = append(r.segments, seg)
	if len(r.segments) > maxSegments {
		r.coalesceSegments()
	}
}

func (r *Renderer) coalesceSegments() {
	merge := len(r.segments) - maxSegments/2
	if merge <= 1 {
		return
	}
	var text strings.Builder
	var plain strings.Builder
	for _, seg := range r.segments[:merge] {
		text.WriteString(seg.Text)
		plain.WriteString(seg.Plain)
	}
	head := Segment{Text: text.String(), Plain: plain.String(), Width: runewidth.StringWidth(lastLine(plain.String()))}
	r.segments[0] = head
	n := copy(r.segments[1:], r.segments[merge:])
	r.segments = r.segments[:n+1]
	for i := range r.commits {
		switch {
		case r.commits[i].end <= merge:
			r.commits[i].end = 1
		default:
			r.commits[i].end -= merge - 1
		}
	}
}

func (r *Renderer) wrapWidth() int {
	return mdMaxInt(1, mdMinInt(r.width-2, maxSegmentChars))
}

func wrapPlain(text string, width int) []string {
	if text == "" {
		return []string{""}
	}
	raw := strings.Split(strings.ReplaceAll(text, "\t", "    "), "\n")
	out := make([]string, 0, len(raw))
	for _, line := range raw {
		out = append(out, wrapLineCap(line, width)...)
	}
	return out
}

func wrapLineCap(line string, width int) []string {
	width = mdMaxInt(1, mdMinInt(width, maxSegmentChars))
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

func trimNonEmpty(lines []string) []string {
	out := make([]string, 0, len(lines))
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line != "" {
			out = append(out, line)
		}
	}
	return out
}

func eventBlock(kind, block BlockKind) BlockKind {
	if block != 0 {
		return block
	}
	return kind
}

func lastLine(s string) string {
	s = strings.TrimSuffix(s, "\n")
	i := strings.LastIndexByte(s, '\n')
	if i < 0 {
		return s
	}
	return s[i+1:]
}

func mdMinInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func mdMaxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func stripANSI(s string) string {
	var b strings.Builder
	for i := 0; i < len(s); i++ {
		if s[i] != 0x1b {
			b.WriteByte(s[i])
			continue
		}
		i++
		if i >= len(s) || s[i] != '[' {
			continue
		}
		for i < len(s) && (s[i] < '@' || s[i] > '~') {
			i++
		}
	}
	return b.String()
}
