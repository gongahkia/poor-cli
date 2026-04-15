package markdown

import (
	"strings"
	"unicode"
)

const inlineHoldbackLimit = 128

type InlineTokenizer struct {
	closed bool
}

func NewInlineTokenizer() *InlineTokenizer {
	return &InlineTokenizer{}
}

func (i *InlineTokenizer) FeedLine(rawLine RawLineEvent) []Event {
	if i.closed {
		i.closed = false
	}
	var out eventBuilder
	parseInline(rawLine.Text, &out)
	return out.events
}

func (i *InlineTokenizer) Close() []Event {
	i.closed = true
	return nil
}

type eventBuilder struct {
	events []Event
}

func (b *eventBuilder) text(s string) {
	if s == "" {
		return
	}
	n := len(b.events)
	if n > 0 {
		if prev, ok := b.events[n-1].(TextEvent); ok {
			prev.Value += s
			b.events[n-1] = prev
			return
		}
	}
	b.events = append(b.events, TextEvent{Value: s})
}

func (b *eventBuilder) open(k InlineKind) {
	b.events = append(b.events, InlineOpenEvent{Kind: k})
}

func (b *eventBuilder) close(k InlineKind) {
	b.events = append(b.events, InlineCloseEvent{Kind: k})
}

func (b *eventBuilder) link(text, url string) {
	b.events = append(b.events, LinkEvent{Text: text, URL: url})
}

func parseInline(s string, out *eventBuilder) {
	textStart := 0
	for p := 0; p < len(s); {
		switch s[p] {
		case '`':
			if end := findCodeClose(s, p); end > p {
				out.text(s[textStart:p])
				out.open(InlineCode)
				out.text(s[p+1 : end])
				out.close(InlineCode)
				p = end + 1
				textStart = p
				continue
			}
		case '[':
			if text, url, end, ok := parseLink(s, p); ok {
				out.text(s[textStart:p])
				out.link(text, url)
				p = end
				textStart = p
				continue
			}
		case '<':
			if url, end, ok := parseAutolink(s, p); ok {
				out.text(s[textStart:p])
				out.link(url, url)
				p = end
				textStart = p
				continue
			}
		case '*', '_':
			if end, n, ok := findEmphasisClose(s, p); ok {
				out.text(s[textStart:p])
				emitEmphasis(s[p+n:end], n, out)
				p = end + n
				textStart = p
				continue
			}
		}
		p++
	}
	out.text(s[textStart:])
}

func findCodeClose(s string, open int) int {
	for p := open + 1; p < len(s); p++ {
		if s[p] == '`' {
			return p
		}
	}
	return -1
}

func parseLink(s string, open int) (string, string, int, bool) {
	if open > 0 && s[open-1] == '!' {
		return "", "", 0, false
	}
	closeText := strings.IndexByte(s[open+1:], ']')
	if closeText < 0 {
		return "", "", 0, false
	}
	closeText += open + 1
	if closeText+1 >= len(s) || s[closeText+1] != '(' {
		return "", "", 0, false
	}
	closeURL := strings.IndexByte(s[closeText+2:], ')')
	if closeURL < 0 {
		return "", "", 0, false
	}
	closeURL += closeText + 2
	url := s[closeText+2 : closeURL]
	if url == "" || strings.ContainsAny(url, " \t\r\n") {
		return "", "", 0, false
	}
	return s[open+1 : closeText], url, closeURL + 1, true
}

func parseAutolink(s string, open int) (string, int, bool) {
	close := strings.IndexByte(s[open+1:], '>')
	if close < 0 {
		return "", 0, false
	}
	close += open + 1
	url := s[open+1 : close]
	if !isStrictURL(url) {
		return "", 0, false
	}
	return url, close + 1, true
}

func isStrictURL(s string) bool {
	colon := strings.IndexByte(s, ':')
	if colon <= 0 {
		return false
	}
	for p, r := range s {
		if unicode.IsSpace(r) || r == '<' || r == '>' {
			return false
		}
		if p == colon {
			break
		}
		if p == 0 {
			if !unicode.IsLetter(r) {
				return false
			}
			continue
		}
		if !unicode.IsLetter(r) && !unicode.IsDigit(r) && r != '+' && r != '.' && r != '-' {
			return false
		}
	}
	return colon+1 < len(s) && strings.HasPrefix(s[colon+1:], "//")
}

func findEmphasisClose(s string, open int) (int, int, bool) {
	ch := s[open]
	run := delimiterRun(s, open)
	canOpen, _ := delimiterFlanking(s, open, run)
	if !canOpen {
		return 0, 0, false
	}
	candidates := emphasisCandidates(run)
	for _, n := range candidates {
		if end, ok := scanEmphasisClose(s, open+n, ch, n); ok {
			return end, n, true
		}
	}
	return 0, 0, false
}

func emphasisCandidates(run int) []int {
	if run >= 3 {
		return []int{3, 2, 1}
	}
	if run >= 2 {
		return []int{2, 1}
	}
	return []int{1}
}

func scanEmphasisClose(s string, start int, ch byte, n int) (int, bool) {
	limit := start + inlineHoldbackLimit
	if limit > len(s) {
		limit = len(s)
	}
	for p := start; p < limit; {
		if skip := inlineAtomEnd(s, p); skip > p {
			p = skip
			continue
		}
		if s[p] != ch {
			p++
			continue
		}
		run := delimiterRun(s, p)
		_, canClose := delimiterFlanking(s, p, run)
		if canClose && closeRunMatches(run, n) {
			return p, true
		}
		p += run
	}
	return 0, false
}

func closeRunMatches(run, n int) bool {
	switch n {
	case 3:
		return run >= 3
	case 2:
		return run >= 2 && run%2 == 0
	default:
		return run%2 == 1
	}
}

func emitEmphasis(content string, n int, out *eventBuilder) {
	switch n {
	case 3:
		out.open(InlineStrong)
		out.open(InlineEmphasis)
		parseInline(content, out)
		out.close(InlineEmphasis)
		out.close(InlineStrong)
	case 2:
		out.open(InlineStrong)
		parseInline(content, out)
		out.close(InlineStrong)
	default:
		out.open(InlineEmphasis)
		parseInline(content, out)
		out.close(InlineEmphasis)
	}
}

func delimiterRun(s string, p int) int {
	ch := s[p]
	q := p
	for q < len(s) && s[q] == ch {
		q++
	}
	return q - p
}

func delimiterFlanking(s string, p, n int) (bool, bool) {
	ch := s[p]
	before, hasBefore := previousRune(s, p)
	after, hasAfter := nextRune(s, p+n)
	beforeSpace := !hasBefore || unicode.IsSpace(before)
	afterSpace := !hasAfter || unicode.IsSpace(after)
	beforePunct := hasBefore && unicode.IsPunct(before)
	afterPunct := hasAfter && unicode.IsPunct(after)
	left := !afterSpace && (!afterPunct || beforeSpace || beforePunct)
	right := !beforeSpace && (!beforePunct || afterSpace || afterPunct)
	if ch == '_' {
		return left && (!right || beforePunct), right && (!left || afterPunct)
	}
	return left, right
}

func previousRune(s string, p int) (rune, bool) {
	if p <= 0 {
		return 0, false
	}
	var last rune
	for _, r := range s[:p] {
		last = r
	}
	return last, true
}

func nextRune(s string, p int) (rune, bool) {
	if p >= len(s) {
		return 0, false
	}
	for _, r := range s[p:] {
		return r, true
	}
	return 0, false
}

func inlineAtomEnd(s string, p int) int {
	switch s[p] {
	case '`':
		if end := findCodeClose(s, p); end > p {
			return end + 1
		}
	case '[':
		if _, _, end, ok := parseLink(s, p); ok {
			return end
		}
	case '<':
		if _, end, ok := parseAutolink(s, p); ok {
			return end
		}
	}
	return p
}
