package markdown

type BlockKind uint8

const (
	BlockParagraph BlockKind = iota
	BlockHeading1
	BlockHeading2
	BlockHeading3
	BlockHeading4
	BlockHeading5
	BlockHeading6
	BlockCodeFence
	BlockBlockquote
	BlockListUnordered
	BlockListOrdered
	BlockListItem
	BlockThematicBreak
)

type InlineKind uint8

const (
	InlineEmphasis InlineKind = iota
	InlineStrong
	InlineCode
	InlineLink
	InlineAutolink
)

type EventKind uint8

const (
	EventBlockOpen EventKind = iota
	EventBlockClose
	EventRawLine
	EventInlineOpen
	EventInlineClose
	EventText
	EventLink
	EventCodeBlockDelta
	EventCommit
)

type Event interface {
	EventKind() EventKind
}

type BlockOpenEvent struct {
	Kind  BlockKind
	Block BlockKind
	Info  string
	Line  int
}

func (BlockOpenEvent) EventKind() EventKind { return EventBlockOpen }

type BlockCloseEvent struct {
	Kind  BlockKind
	Block BlockKind
	Line  int
}

func (BlockCloseEvent) EventKind() EventKind { return EventBlockClose }

type RawLineEvent struct {
	Kind  BlockKind
	Block BlockKind
	Text  string
	Line  int
}

func (RawLineEvent) EventKind() EventKind { return EventRawLine }

type InlineOpenEvent struct{ Kind InlineKind }

func (InlineOpenEvent) EventKind() EventKind { return EventInlineOpen }

type InlineCloseEvent struct{ Kind InlineKind }

func (InlineCloseEvent) EventKind() EventKind { return EventInlineClose }

type TextEvent struct{ Value string }

func (TextEvent) EventKind() EventKind { return EventText }

type LinkEvent struct {
	Text string
	URL  string
}

func (LinkEvent) EventKind() EventKind { return EventLink }

type CodeBlockDeltaEvent struct {
	Lang  string
	Line  string
	Final bool
}

func (CodeBlockDeltaEvent) EventKind() EventKind { return EventCodeBlockDelta }

type CommitEvent struct {
	Mark     uint64
	UpToLine int
}

func (CommitEvent) EventKind() EventKind { return EventCommit }
