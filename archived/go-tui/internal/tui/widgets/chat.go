package widgets

import (
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/config"
	"github.com/gongahkia/gocli-poor/internal/markdown"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/tui/emptystate"
	"github.com/mattn/go-runewidth"
)

const frameInterval = time.Second / 60

type ChatDeps struct {
	Theme      *theme.Theme
	MDRenderer markdown.LineRenderer
	Keymap     *config.Keymap
}

type ChatView struct {
	theme       *theme.Theme
	mdRenderer  markdown.LineRenderer
	keymap      *config.Keymap
	messages    []state.Message
	multiplayer state.MultiplayerState
	rendered    []renderedMsg
	viewport    viewport
	width       int
	height      int
	expanded    map[string]bool
	focusedTool string
	lastFrame   time.Time
	dirty       bool
	viewCache   string
	rowScratch  []string
}

type renderedMsg struct {
	id          string
	raw         state.Message
	blocks      []string
	totalHeight int
}

type viewport struct {
	topIdx    int
	topOffset int
	height    int
}

type frameMsg time.Time

func NewChat(t *theme.Theme, mdRenderer markdown.LineRenderer) *ChatView {
	return NewChatView(ChatDeps{Theme: t, MDRenderer: mdRenderer})
}

func New(t *theme.Theme, mdRenderer markdown.LineRenderer) *ChatView {
	return NewChat(t, mdRenderer)
}

func NewChatView(d ChatDeps) *ChatView {
	t := d.Theme
	if t == nil {
		builtin := theme.DarkWithCapability(theme.CapabilityMonochrome)
		t = &builtin
	}
	if d.MDRenderer == nil {
		d.MDRenderer = markdown.NewPlainRenderer()
	}
	return &ChatView{
		theme:      t,
		mdRenderer: d.MDRenderer,
		keymap:     d.Keymap,
		width:      80,
		expanded:   map[string]bool{},
		dirty:      true,
	}
}

func (c *ChatView) Update(msg tea.Msg) (*ChatView, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "pgup", "ctrl+u":
			c.ScrollUp(maxInt(1, c.viewport.height))
		case "pgdown", "ctrl+d":
			c.ScrollDown(maxInt(1, c.viewport.height))
		case "home":
			c.ScrollToTop()
		case "end":
			c.ScrollToBottom()
		case "up", "k":
			c.ScrollUp(1)
		case "down", "j":
			c.ScrollDown(1)
		case "enter", " ":
			c.toggleFocusedTool()
		}
	case tea.MouseMsg:
		switch msg.Button {
		case tea.MouseButtonWheelUp:
			c.ScrollUp(3)
		case tea.MouseButtonWheelDown:
			c.ScrollDown(3)
		}
	case frameMsg:
		c.lastFrame = time.Time(msg)
		c.dirty = false
		return c, nil
	}
	if c.dirty {
		return c, c.frameCmd()
	}
	return c, nil
}

func (c *ChatView) View(width, height int) string {
	width = maxInt(0, width)
	height = maxInt(0, height)
	oldAbs := c.absoluteTop()
	oldBottom := c.IsAtBottom()
	if width != c.width {
		c.width = width
		c.rebuildRendered()
	}
	if height != c.height {
		c.height = height
		c.viewport.height = height
	}
	if oldBottom {
		c.ScrollToBottom()
	} else {
		c.setAbsoluteTop(oldAbs)
	}
	if !c.dirty && c.viewCache != "" {
		return c.viewCache
	}
	now := time.Now()
	if !c.lastFrame.IsZero() && now.Sub(c.lastFrame) < frameInterval && c.viewCache != "" {
		return c.viewCache
	}
	rows := c.visibleRows()
	if len(c.messages) == 0 {
		rows = []string{"", emptystate.EmptyStateFor(emptystate.FreshLaunch).Render(c.theme)}
	}
	for len(rows) < height {
		rows = append(rows, "")
	}
	if len(rows) > height {
		rows = rows[:height]
	}
	c.viewCache = strings.Join(rows, "\n")
	c.lastFrame = now
	c.dirty = false
	return c.viewCache
}

func (c *ChatView) SetMessages(msgs []state.Message) {
	wasBottom := c.IsAtBottom()
	c.messages = cloneMessages(msgs)
	c.rebuildRendered()
	if wasBottom || c.absoluteTop() == 0 {
		c.ScrollToBottom()
	} else {
		c.clampViewport()
	}
	c.markDirty()
}

func (c *ChatView) SetMultiplayer(mp state.MultiplayerState) {
	c.multiplayer = mp
	c.rebuildRendered()
	c.markDirty()
}

func (c *ChatView) AppendChunk(requestID string, chunk string, segs ...[]markdown.Segment) {
	atBottom := c.IsAtBottom()
	i := c.tailIndex(requestID)
	if i < 0 {
		return
	}
	prevEmpty := c.messages[i].Content == ""
	c.messages[i].Content += chunk
	tail := markdownSegments(segs)
	if len(segs) > 0 {
		for _, seg := range segs[0] {
			c.messages[i].Segments = append(c.messages[i].Segments, state.MarkdownSegment{Text: seg.Text, Plain: seg.Plain, Width: seg.Width})
		}
	}
	if !c.appendRenderedTail(i, prevEmpty, tail) {
		c.renderIndex(i)
	}
	if atBottom {
		c.ScrollToBottom()
	} else {
		c.clampViewport()
	}
	c.markDirty()
}

func (c *ChatView) ScrollUp(n int) {
	c.setAbsoluteTop(c.absoluteTop() - maxInt(0, n))
	c.markDirty()
}

func (c *ChatView) ScrollDown(n int) {
	c.setAbsoluteTop(c.absoluteTop() + maxInt(0, n))
	c.markDirty()
}

func (c *ChatView) ScrollToBottom() {
	c.setAbsoluteTop(maxInt(0, c.totalRows()-c.viewport.height))
	c.markDirty()
}

func (c *ChatView) ScrollToTop() {
	c.setAbsoluteTop(0)
	c.markDirty()
}

func (c *ChatView) IsAtBottom() bool {
	total := c.totalRows()
	if total == 0 || c.viewport.height == 0 {
		return true
	}
	return c.absoluteTop()+c.viewport.height >= total
}

func (c *ChatView) rebuildRendered() {
	c.rendered = make([]renderedMsg, len(c.messages))
	for i := range c.messages {
		c.renderIndex(i)
	}
	c.ensureFocusedTool()
}

func (c *ChatView) renderIndex(i int) {
	if i < 0 || i >= len(c.messages) {
		return
	}
	rm := renderMessage(c.messages[i], c.theme, c.mdRenderer, maxInt(1, c.width), c.expanded, c.multiplayer)
	if i < len(c.messages)-1 {
		rm.blocks = append(rm.blocks, "")
		rm.totalHeight = len(rm.blocks)
	}
	c.rendered[i] = rm
}

func (c *ChatView) tailIndex(requestID string) int {
	for i := len(c.messages) - 1; i >= 0; i-- {
		if c.messages[i].RequestID == requestID {
			return i
		}
	}
	return -1
}

func (c *ChatView) totalRows() int {
	total := 0
	for _, msg := range c.rendered {
		total += msg.totalHeight
	}
	return total
}

func (c *ChatView) absoluteTop() int {
	row := c.viewport.topOffset
	for i := 0; i < c.viewport.topIdx && i < len(c.rendered); i++ {
		row += c.rendered[i].totalHeight
	}
	return clampInt(row, 0, maxInt(0, c.totalRows()-c.viewport.height))
}

func (c *ChatView) setAbsoluteTop(row int) {
	row = clampInt(row, 0, maxInt(0, c.totalRows()-c.viewport.height))
	for i, msg := range c.rendered {
		if row < msg.totalHeight {
			c.viewport.topIdx = i
			c.viewport.topOffset = row
			return
		}
		row -= msg.totalHeight
	}
	c.viewport.topIdx = maxInt(0, len(c.rendered)-1)
	c.viewport.topOffset = 0
}

func (c *ChatView) clampViewport() {
	c.setAbsoluteTop(c.absoluteTop())
}

func (c *ChatView) visibleRows() []string {
	if c.height <= 0 || len(c.rendered) == 0 {
		return nil
	}
	rows := c.rowScratch[:0]
	i := c.viewport.topIdx
	offset := c.viewport.topOffset
	for i < len(c.rendered) && len(rows) < c.height {
		msg := c.rendered[i]
		if offset < msg.totalHeight {
			rows = append(rows, msg.blocks[offset:]...)
		}
		i++
		offset = 0
	}
	if len(rows) > c.height {
		rows = rows[:c.height]
	}
	c.rowScratch = rows
	return rows
}

func (c *ChatView) appendRenderedTail(i int, prevEmpty bool, tail []state.MarkdownSegment) bool {
	if i < 0 || i >= len(c.messages) || len(tail) == 0 {
		return false
	}
	msg := c.messages[i]
	if msg.Role != state.RoleAssistant || len(msg.ToolCalls) > 0 {
		return false
	}
	lines := segmentTextLines(tail)
	if len(lines) == 0 {
		return true
	}
	label := messageLabel(msg, c.multiplayer)
	prefix := rolePrefix(label, c.theme) + " "
	prefixWidth := runewidth.StringWidth(label) + 1
	indent := strings.Repeat(" ", prefixWidth)
	rm := &c.rendered[i]
	if prevEmpty || len(rm.blocks) == 0 || (len(rm.blocks) == 1 && rm.raw.Content == "") {
		rm.blocks = rm.blocks[:0]
		rm.blocks = append(rm.blocks, prefix+lines[0])
		lines = lines[1:]
	}
	for _, line := range lines {
		rm.blocks = append(rm.blocks, indent+line)
	}
	rm.raw = msg
	rm.totalHeight = len(rm.blocks)
	return true
}

func markdownSegments(segs [][]markdown.Segment) []state.MarkdownSegment {
	if len(segs) == 0 || len(segs[0]) == 0 {
		return nil
	}
	out := make([]state.MarkdownSegment, len(segs[0]))
	for i, seg := range segs[0] {
		out[i] = state.MarkdownSegment{Text: seg.Text, Plain: seg.Plain, Width: seg.Width}
	}
	return out
}

func segmentTextLines(segs []state.MarkdownSegment) []string {
	lines := make([]string, 0, len(segs))
	for _, seg := range segs {
		line := seg.Text
		if line == "" {
			line = seg.Plain
		}
		lines = append(lines, strings.TrimSuffix(line, "\n"))
	}
	return lines
}

func (c *ChatView) toggleFocusedTool() {
	key := c.focusedTool
	if key == "" {
		key = c.firstToolKey()
	}
	if key == "" {
		return
	}
	c.expanded[key] = !c.expanded[key]
	c.rebuildRendered()
	c.markDirty()
}

func (c *ChatView) firstToolKey() string {
	for _, msg := range c.messages {
		for _, call := range msg.ToolCalls {
			return toolKey(call)
		}
	}
	return ""
}

func (c *ChatView) ensureFocusedTool() {
	if c.focusedTool == "" {
		c.focusedTool = c.firstToolKey()
	}
}

func (c *ChatView) frameCmd() tea.Cmd {
	return tea.Tick(frameInterval, func(t time.Time) tea.Msg { return frameMsg(t) })
}

func (c *ChatView) markDirty() {
	c.dirty = true
	c.viewCache = ""
}

func cloneMessages(in []state.Message) []state.Message {
	if in == nil {
		return nil
	}
	out := make([]state.Message, len(in))
	for i, msg := range in {
		out[i] = msg
		out[i].Segments = append([]state.MarkdownSegment(nil), msg.Segments...)
		out[i].ToolCalls = append([]state.ToolCall(nil), msg.ToolCalls...)
		for j := range out[i].ToolCalls {
			out[i].ToolCalls[j].Chunks = append([]string(nil), msg.ToolCalls[j].Chunks...)
		}
	}
	return out
}

func clampInt(v, lo, hi int) int {
	if hi < lo {
		hi = lo
	}
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}
