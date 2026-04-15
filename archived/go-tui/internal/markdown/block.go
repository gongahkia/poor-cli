package markdown

import (
	"bytes"
	"strings"
	"unicode"
)

type BlockTokenizer struct {
	buf       []byte
	line      int
	lastLine  int
	out       []Event
	pending   []Event
	open      []BlockKind
	closed    bool
	codeInfo  string
	fenceChar byte
	fenceLen  int
	listKind  BlockKind
	itemOpen  bool
}

func NewBlockTokenizer() *BlockTokenizer {
	return &BlockTokenizer{line: 1}
}

func (b *BlockTokenizer) Write(chunk []byte) {
	if b.closed || len(chunk) == 0 {
		return
	}
	b.buf = append(b.buf, chunk...)
	b.scan(false)
}

func (b *BlockTokenizer) Drain() []Event {
	if len(b.out) == 0 {
		return nil
	}
	out := b.out
	b.out = nil
	return out
}

func (b *BlockTokenizer) Close() []Event {
	if b.closed {
		return nil
	}
	b.closed = true
	b.scan(true)
	if b.in(BlockParagraph) {
		b.closeParagraph(b.lastLine)
	}
	if b.in(BlockBlockquote) {
		b.closeBlockquote(b.lastLine)
	}
	if b.inList() {
		b.closeList(b.lastLine)
	}
	if b.in(BlockCodeFence) {
		b.closeCodeFence(b.lastLine)
	}
	return b.Drain()
}

func (b *BlockTokenizer) scan(final bool) {
	for {
		i := bytes.IndexByte(b.buf, '\n')
		if i < 0 {
			break
		}
		line := string(dropCR(b.buf[:i]))
		b.buf = b.buf[i+1:]
		b.processLine(line)
		b.lastLine = b.line
		b.line++
	}
	if final && len(b.buf) > 0 {
		line := string(dropCR(b.buf))
		b.buf = nil
		b.processLine(line)
		b.lastLine = b.line
		b.line++
	}
}

func dropCR(line []byte) []byte {
	if len(line) > 0 && line[len(line)-1] == '\r' {
		return line[:len(line)-1]
	}
	return line
}

func (b *BlockTokenizer) processLine(line string) {
	for {
		if b.in(BlockCodeFence) {
			b.processCodeLine(line)
			return
		}
		if b.inList() {
			if b.processListLine(line) {
				return
			}
			continue
		}
		if b.in(BlockBlockquote) {
			if b.processBlockquoteLine(line) {
				return
			}
			continue
		}
		if b.in(BlockParagraph) {
			if b.processParagraphLine(line) {
				return
			}
			continue
		}
		b.processStartLine(line)
		return
	}
}

func (b *BlockTokenizer) processStartLine(line string) {
	stripped, _ := stripUpTo3Spaces(line)
	if isBlank(stripped) {
		b.commit(b.line)
		return
	}
	if isThematicBreak(stripped) {
		b.pending = append(b.pending, blockOpen(BlockThematicBreak, "", b.line), rawLine(BlockThematicBreak, stripped, b.line), blockClose(BlockThematicBreak, b.line))
		b.commit(b.line)
		return
	}
	if level, text, ok := parseHeading(stripped); ok {
		kind := BlockKind(int(BlockHeading1) + level - 1)
		b.pending = append(b.pending, blockOpen(kind, "", b.line), rawLine(kind, text, b.line), blockClose(kind, b.line))
		b.commit(b.line)
		return
	}
	if marker, n, info, ok := parseFenceOpen(stripped); ok {
		b.openBlock(BlockCodeFence, info)
		b.codeInfo = info
		b.fenceChar = marker
		b.fenceLen = n
		return
	}
	if text, ok := parseBlockquote(stripped); ok {
		b.openBlock(BlockBlockquote, "")
		b.pending = append(b.pending, rawLine(BlockBlockquote, text, b.line))
		return
	}
	if text, ok := parseUnorderedItem(stripped); ok {
		b.openList(BlockListUnordered, "", text)
		return
	}
	if start, text, ok := parseOrderedItem(stripped); ok {
		b.openList(BlockListOrdered, start, text)
		return
	}
	b.openBlock(BlockParagraph, "")
	b.pending = append(b.pending, rawLine(BlockParagraph, line, b.line))
}

func (b *BlockTokenizer) processCodeLine(line string) {
	stripped, _ := stripUpTo3Spaces(line)
	if isFenceClose(stripped, b.fenceChar, b.fenceLen) {
		b.closeCodeFence(b.line)
		return
	}
	b.pending = append(b.pending, rawLine(BlockCodeFence, line, b.line))
}

func (b *BlockTokenizer) processParagraphLine(line string) bool {
	stripped, _ := stripUpTo3Spaces(line)
	if isBlank(stripped) {
		b.closeParagraph(b.line)
		return true
	}
	if startsInterruptingBlock(stripped) {
		b.closeParagraph(b.lastLine)
		return false
	}
	b.pending = append(b.pending, rawLine(BlockParagraph, line, b.line))
	return true
}

func (b *BlockTokenizer) processBlockquoteLine(line string) bool {
	stripped, _ := stripUpTo3Spaces(line)
	if text, ok := parseBlockquote(stripped); ok {
		b.pending = append(b.pending, rawLine(BlockBlockquote, text, b.line))
		return true
	}
	b.closeBlockquote(b.lastLine)
	return isBlank(stripped)
}

func (b *BlockTokenizer) processListLine(line string) bool {
	stripped, _ := stripUpTo3Spaces(line)
	if isBlank(stripped) {
		b.closeList(b.line)
		return true
	}
	if b.listKind == BlockListUnordered {
		if text, ok := parseUnorderedItem(stripped); ok {
			b.closeListItem(b.lastLine)
			b.openListItem(text)
			return true
		}
	} else if _, text, ok := parseOrderedItem(stripped); ok {
		b.closeListItem(b.lastLine)
		b.openListItem(text)
		return true
	}
	if text, ok := parseListContinuation(line); ok {
		b.pending = append(b.pending, rawLine(BlockListItem, text, b.line))
		return true
	}
	b.closeList(b.lastLine)
	return false
}

func (b *BlockTokenizer) openBlock(kind BlockKind, info string) {
	b.open = append(b.open, kind)
	b.pending = append(b.pending, blockOpen(kind, info, b.line))
}

func (b *BlockTokenizer) closeParagraph(line int) {
	if !b.pop(BlockParagraph) {
		return
	}
	b.pending = append(b.pending, blockClose(BlockParagraph, line))
	b.commit(line)
}

func (b *BlockTokenizer) closeBlockquote(line int) {
	if !b.pop(BlockBlockquote) {
		return
	}
	b.pending = append(b.pending, blockClose(BlockBlockquote, line))
	b.commit(line)
}

func (b *BlockTokenizer) closeCodeFence(line int) {
	if !b.pop(BlockCodeFence) {
		return
	}
	b.pending = append(b.pending, blockClose(BlockCodeFence, line))
	b.codeInfo = ""
	b.fenceChar = 0
	b.fenceLen = 0
	b.commit(line)
}

func (b *BlockTokenizer) openList(kind BlockKind, info, text string) {
	b.listKind = kind
	b.open = append(b.open, kind)
	b.pending = append(b.pending, blockOpen(kind, info, b.line))
	b.openListItem(text)
}

func (b *BlockTokenizer) openListItem(text string) {
	b.itemOpen = true
	b.open = append(b.open, BlockListItem)
	b.pending = append(b.pending, blockOpen(BlockListItem, "", b.line), rawLine(BlockListItem, text, b.line))
}

func (b *BlockTokenizer) closeListItem(line int) {
	if !b.itemOpen {
		return
	}
	b.pop(BlockListItem)
	b.itemOpen = false
	b.pending = append(b.pending, blockClose(BlockListItem, line))
}

func (b *BlockTokenizer) closeList(line int) {
	kind := b.listKind
	b.closeListItem(line)
	if !b.pop(kind) {
		return
	}
	b.pending = append(b.pending, blockClose(kind, line))
	b.listKind = 0
	b.commit(line)
}

func (b *BlockTokenizer) commit(line int) {
	if len(b.pending) > 0 {
		b.out = append(b.out, b.pending...)
		b.pending = nil
	}
	b.out = append(b.out, CommitEvent{UpToLine: line})
}

func (b *BlockTokenizer) in(kind BlockKind) bool {
	return len(b.open) > 0 && b.open[len(b.open)-1] == kind
}

func (b *BlockTokenizer) inList() bool {
	return b.listKind == BlockListUnordered || b.listKind == BlockListOrdered
}

func (b *BlockTokenizer) pop(kind BlockKind) bool {
	if len(b.open) == 0 || b.open[len(b.open)-1] != kind {
		return false
	}
	b.open = b.open[:len(b.open)-1]
	return true
}

func stripUpTo3Spaces(line string) (string, int) {
	n := 0
	for n < len(line) && n < 3 && line[n] == ' ' {
		n++
	}
	return line[n:], n
}

func isBlank(line string) bool {
	return strings.TrimSpace(line) == ""
}

func isThematicBreak(line string) bool {
	return line == "---" || line == "***" || line == "___"
}

func parseHeading(line string) (int, string, bool) {
	n := 0
	for n < len(line) && n < 6 && line[n] == '#' {
		n++
	}
	if n == 0 || n >= len(line) || line[n] != ' ' {
		return 0, "", false
	}
	return n, line[n+1:], true
}

func parseFenceOpen(line string) (byte, int, string, bool) {
	if len(line) < 3 || (line[0] != '`' && line[0] != '~') {
		return 0, 0, "", false
	}
	marker := line[0]
	n := 0
	for n < len(line) && line[n] == marker {
		n++
	}
	if n < 3 {
		return 0, 0, "", false
	}
	return marker, n, strings.TrimSpace(line[n:]), true
}

func isFenceClose(line string, marker byte, n int) bool {
	if len(line) < n {
		return false
	}
	i := 0
	for i < len(line) && line[i] == marker {
		i++
	}
	return i >= n && strings.TrimSpace(line[i:]) == ""
}

func parseBlockquote(line string) (string, bool) {
	if len(line) < 2 || line[0] != '>' || line[1] != ' ' {
		return "", false
	}
	return line[2:], true
}

func parseUnorderedItem(line string) (string, bool) {
	if len(line) < 2 || line[1] != ' ' {
		return "", false
	}
	switch line[0] {
	case '-', '+', '*':
		return line[2:], true
	default:
		return "", false
	}
}

func parseOrderedItem(line string) (string, string, bool) {
	i := 0
	for i < len(line) && unicode.IsDigit(rune(line[i])) {
		i++
	}
	if i == 0 || i+1 >= len(line) || line[i] != '.' || line[i+1] != ' ' {
		return "", "", false
	}
	return line[:i], line[i+2:], true
}

func parseListContinuation(line string) (string, bool) {
	spaces := 0
	for i := 0; i < len(line); i++ {
		switch line[i] {
		case ' ':
			spaces++
		case '\t':
			spaces += 4
		default:
			if spaces < 2 {
				return "", false
			}
			return strings.TrimLeft(line, " \t"), true
		}
	}
	return "", false
}

func startsInterruptingBlock(line string) bool {
	if isThematicBreak(line) {
		return true
	}
	if _, _, ok := parseHeading(line); ok {
		return true
	}
	if _, _, _, ok := parseFenceOpen(line); ok {
		return true
	}
	if _, ok := parseBlockquote(line); ok {
		return true
	}
	if _, ok := parseUnorderedItem(line); ok {
		return true
	}
	_, _, ok := parseOrderedItem(line)
	return ok
}

func blockOpen(kind BlockKind, info string, line int) BlockOpenEvent {
	return BlockOpenEvent{Kind: kind, Info: info, Line: line}
}

func blockClose(kind BlockKind, line int) BlockCloseEvent {
	return BlockCloseEvent{Kind: kind, Line: line}
}

func rawLine(kind BlockKind, text string, line int) RawLineEvent {
	return RawLineEvent{Kind: kind, Text: text, Line: line}
}
