package markdown

import "github.com/gongahkia/gocli-poor/internal/theme"

type Streamer struct {
	blocks   *BlockTokenizer
	inline   *InlineTokenizer
	renderer *Renderer
	pending  []Event
	inCode   bool
	codeLang string
	closed   bool
}

func NewStreamer(t *theme.Theme, highlighter *Highlighter, width int) *Streamer {
	return &Streamer{
		blocks:   NewBlockTokenizer(),
		inline:   NewInlineTokenizer(),
		renderer: NewRenderer(t, highlighter, width),
	}
}

func NewStreamerWithDeps(d RendererDeps) *Streamer {
	return NewStreamer(d.Theme, d.Highlighter, d.Width)
}

func (s *Streamer) Write(chunk []byte) {
	if s.closed || len(chunk) == 0 {
		return
	}
	s.blocks.Write(chunk)
	s.feed(s.blocks.Drain())
}

func (s *Streamer) Drain() ([]Event, string) {
	events := s.pending
	s.pending = nil
	return events, ""
}

func (s *Streamer) Mark() Mark {
	return s.renderer.Mark()
}

func (s *Streamer) TailSince(mark Mark) (string, Mark) {
	return s.renderer.TailSince(mark)
}

func (s *Streamer) Full() string {
	return s.renderer.Full()
}

func (s *Streamer) Resize(width int) {
	s.renderer.Resize(width)
}

func (s *Streamer) Close() string {
	if s.closed {
		return ""
	}
	prev := s.Mark()
	s.closed = true
	s.feed(s.blocks.Close())
	s.inline.Close()
	tail, _ := s.renderer.TailSince(prev)
	return tail
}

func (s *Streamer) feed(events []Event) {
	if len(events) == 0 {
		return
	}
	expanded := s.expand(events)
	s.pending = append(s.pending, expanded...)
	s.renderer.Feed(expanded)
}

func (s *Streamer) expand(events []Event) []Event {
	if !s.inCode && !hasCodeFenceEvent(events) {
		return events
	}
	out := make([]Event, 0, len(events))
	for _, event := range events {
		switch e := event.(type) {
		case BlockOpenEvent:
			kind := eventBlock(e.Kind, e.Block)
			if kind == BlockCodeFence {
				s.inCode = true
				s.codeLang = normalizeLang(e.Info)
			}
			out = append(out, event)
		case BlockCloseEvent:
			if eventBlock(e.Kind, e.Block) == BlockCodeFence {
				s.inCode = false
				s.codeLang = ""
			}
			out = append(out, event)
		case RawLineEvent:
			if s.inCode || eventBlock(e.Kind, e.Block) == BlockCodeFence {
				out = append(out, CodeBlockDeltaEvent{Lang: s.codeLang, Line: e.Text, Final: true})
				continue
			}
			out = append(out, event)
		default:
			out = append(out, event)
		}
	}
	return out
}

func hasCodeFenceEvent(events []Event) bool {
	for _, event := range events {
		switch e := event.(type) {
		case BlockOpenEvent:
			if eventBlock(e.Kind, e.Block) == BlockCodeFence {
				return true
			}
		case BlockCloseEvent:
			if eventBlock(e.Kind, e.Block) == BlockCodeFence {
				return true
			}
		case RawLineEvent:
			if eventBlock(e.Kind, e.Block) == BlockCodeFence {
				return true
			}
		}
	}
	return false
}
