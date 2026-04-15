package flows

import (
	"context"
	"sync"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
)

const (
	typingDebounce = 250 * time.Millisecond
	typingIdle     = 2 * time.Second
)

type LocalInputChangedMsg struct{}
type LocalInputSubmittedMsg struct{}

type typingIdleMsg struct {
	seq int
}

type PresenceFlow struct {
	rpc     Notifier
	state   StateDispatcher
	context func() context.Context
	now     func() time.Time

	mu       sync.Mutex
	unsubs   []func()
	typing   bool
	lastTrue time.Time
	idleSeq  int
}

func NewPresenceFlow(d Deps) *PresenceFlow {
	f := &PresenceFlow{state: d.State, context: d.Context, now: d.Now}
	if n, ok := d.RPC.(Notifier); ok {
		f.rpc = n
	}
	if f.state == nil && d.Store != nil {
		f.state = d.Store
	}
	if f.context == nil {
		f.context = context.Background
	}
	if f.now == nil {
		f.now = time.Now
	}
	return f
}

func (p *PresenceFlow) Name() string { return "presence" }

func (p *PresenceFlow) StartFlow(_ context.Context, d Deps) error {
	p.applyDeps(d)
	if sub, ok := d.RPC.(NotificationSubscriber); ok {
		p.unsubs = append(p.unsubs, sub.Subscribe(protocol.MethodMemberTyping, p.onMemberTyping))
	}
	return nil
}

func (p *PresenceFlow) Stop() error {
	for _, unsub := range p.unsubs {
		unsub()
	}
	p.unsubs = nil
	p.sendTyping(false)
	return nil
}

func (p *PresenceFlow) Update(msg tea.Msg) tea.Cmd {
	switch msg := msg.(type) {
	case LocalInputChangedMsg:
		return p.noteTyping()
	case LocalInputSubmittedMsg:
		p.markIdle()
	case widgets.SubmitMsg:
		p.markIdle()
	case typingIdleMsg:
		p.markIdleIfCurrent(msg.seq)
	}
	return nil
}

func (p *PresenceFlow) noteTyping() tea.Cmd {
	now := p.timeNow()
	p.mu.Lock()
	p.idleSeq++
	seq := p.idleSeq
	shouldSend := !p.typing || p.lastTrue.IsZero() || now.Sub(p.lastTrue) >= typingDebounce
	p.typing = true
	if shouldSend {
		p.lastTrue = now
	}
	p.mu.Unlock()
	if shouldSend {
		p.notify(true)
	}
	return tea.Tick(typingIdle, func(time.Time) tea.Msg { return typingIdleMsg{seq: seq} })
}

func (p *PresenceFlow) markIdle() {
	p.mu.Lock()
	if !p.typing {
		p.mu.Unlock()
		return
	}
	p.idleSeq++
	p.typing = false
	p.lastTrue = time.Time{}
	p.mu.Unlock()
	p.notify(false)
}

func (p *PresenceFlow) markIdleIfCurrent(seq int) {
	p.mu.Lock()
	if !p.typing || seq != p.idleSeq {
		p.mu.Unlock()
		return
	}
	p.typing = false
	p.lastTrue = time.Time{}
	p.mu.Unlock()
	p.notify(false)
}

func (p *PresenceFlow) sendTyping(typing bool) {
	if typing {
		_ = p.noteTyping()
		return
	}
	p.markIdle()
}

func (p *PresenceFlow) notify(typing bool) {
	if p.rpc == nil {
		return
	}
	_ = p.rpc.Notify(p.context(), protocol.MethodSetTyping, protocol.SetTypingParams{Typing: typing})
}

func (p *PresenceFlow) onMemberTyping(params any) {
	var update protocol.MemberTypingNotification
	if !decodeNotification(params, &update) {
		return
	}
	connectionID := firstNonEmptyPresence(update.ConnectionID, update.ConnectionIDAlt)
	if connectionID == "" {
		return
	}
	p.dispatch(state.ActionUpdateMemberTyping{
		ConnectionID: connectionID,
		DisplayName:  firstNonEmptyPresence(update.DisplayName, update.DisplayNameAlt),
		Typing:       update.Typing,
		At:           p.timeNow(),
	})
}

func (p *PresenceFlow) dispatch(action state.Action) {
	if p.state != nil {
		p.state.Dispatch(action)
	}
}

func (p *PresenceFlow) applyDeps(d Deps) {
	if p.state == nil {
		p.state = d.State
	}
	if p.state == nil && d.Store != nil {
		p.state = d.Store
	}
	if p.rpc == nil {
		if n, ok := d.RPC.(Notifier); ok {
			p.rpc = n
		}
	}
	if p.context == nil {
		p.context = d.Context
	}
	if p.context == nil {
		p.context = context.Background
	}
	if p.now == nil {
		p.now = d.Now
	}
	if p.now == nil {
		p.now = time.Now
	}
}

func (p *PresenceFlow) timeNow() time.Time {
	if p.now == nil {
		return time.Now()
	}
	return p.now()
}

func firstNonEmptyPresence(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}
