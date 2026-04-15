package flows

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
)

const chatToastTTL = 3 * time.Second

type NotificationHandler func(params any)

type NotificationSubscriber interface {
	Subscribe(method string, handler NotificationHandler) func()
}

type ChatRPC interface {
	RPCClient
	Notifier
	NotificationSubscriber
}

type ChatFlow struct {
	rpc     RPCClient
	state   StateDispatcher
	store   *state.Store
	context func() context.Context
	now     func() time.Time

	mu        sync.Mutex
	active    map[string]*chatStream
	cancelled map[string]struct{}
	wg        sync.WaitGroup
}

type chatStream struct {
	requestID string
	cancel    context.CancelFunc
	unsubs    []func()
}

type StreamStartedMsg struct{ RequestID string }
type StreamChunkMsg struct{ RequestID, Chunk string }
type StreamEndedMsg struct {
	RequestID string
	Reason    string
	Error     error
}

func NewChatFlow(d Deps) *ChatFlow {
	f := &ChatFlow{
		rpc:       d.RPC,
		state:     d.State,
		store:     d.Store,
		context:   d.Context,
		now:       time.Now,
		active:    map[string]*chatStream{},
		cancelled: map[string]struct{}{},
	}
	if f.state == nil && d.Store != nil {
		f.state = d.Store
	}
	if f.context == nil {
		f.context = context.Background
	}
	return f
}

func (c *ChatFlow) Name() string { return "chat" }

func (c *ChatFlow) Start(text string, ctxFiles []string) {
	text = strings.TrimSpace(text)
	if text == "" {
		return
	}
	rpc, ok := c.rpc.(ChatRPC)
	if !ok {
		c.toast("chat rpc unavailable")
		return
	}
	requestID := newRequestID()
	started := c.timeNow()
	ctx, cancel := context.WithCancel(c.context())
	params := protocol.ChatStreamingParams{
		Message:      text,
		ContextFiles: append([]string(nil), ctxFiles...),
		RequestID:    requestID,
	}
	stream := &chatStream{requestID: requestID, cancel: cancel}
	stream.unsubs = c.subscribeAll(rpc, requestID)
	c.addActive(stream)
	c.dispatch(state.ActionAppendMessage{Msg: state.Message{
		ID:                 "user-" + requestID,
		Role:               state.RoleUser,
		Content:            text,
		AuthorConnectionID: "local",
		CreatedAt:          started,
	}})
	c.dispatch(state.ActionAppendMessage{Msg: state.Message{
		ID:        "assistant-" + requestID,
		Role:      state.RoleAssistant,
		RequestID: requestID,
		Streaming: true,
		CreatedAt: started,
	}})
	c.dispatch(state.ActionStartStream{
		RequestID:      requestID,
		AssistantMsgID: "assistant-" + requestID,
		StartedAt:      started,
		CancelFn:       cancel,
	})
	c.wg.Add(1)
	go c.callChat(ctx, rpc, params)
}

func (c *ChatFlow) Cancel(requestID string) {
	if requestID == "" {
		requestID = c.currentRequestID()
	}
	if requestID == "" {
		return
	}
	rpc, _ := c.rpc.(Notifier)
	if rpc != nil {
		_ = rpc.Notify(context.Background(), protocol.MethodCancelRequest, protocol.CancelParams{RequestID: requestID})
	}
	if stream := c.removeActive(requestID, true); stream != nil {
		stream.cancel()
	}
	c.mu.Lock()
	c.cancelled[requestID] = struct{}{}
	c.mu.Unlock()
	c.dispatch(state.ActionCancelInFlight{})
	c.dispatch(state.ActionEndStream{RequestID: requestID, Reason: "cancelled"})
}

func (c *ChatFlow) Stop() error {
	c.mu.Lock()
	streams := make([]*chatStream, 0, len(c.active))
	for requestID, stream := range c.active {
		streams = append(streams, stream)
		c.cancelled[requestID] = struct{}{}
	}
	c.active = map[string]*chatStream{}
	c.mu.Unlock()
	for _, stream := range streams {
		stream.cancel()
		for _, unsub := range stream.unsubs {
			unsub()
		}
	}
	c.wg.Wait()
	return nil
}

func (c *ChatFlow) Update(msg tea.Msg) tea.Cmd {
	switch msg := msg.(type) {
	case widgets.SubmitMsg:
		c.Start(msg.Text, nil)
	case widgets.CancelMsg:
		c.Cancel("")
	}
	return nil
}

func (c *ChatFlow) callChat(ctx context.Context, rpc ChatRPC, params protocol.ChatStreamingParams) {
	defer c.wg.Done()
	var result protocol.ChatResult
	err := rpc.Call(ctx, protocol.MethodChatStreaming, params, &result)
	requestID := params.RequestID
	if c.isCancelled(requestID) || ctx.Err() != nil {
		c.removeActive(requestID, false)
		return
	}
	if err != nil {
		c.dispatch(state.ActionEndStream{RequestID: requestID, Reason: "error"})
		c.toast(fmt.Sprintf("chat stream failed: %v", err))
		c.removeActive(requestID, false)
		return
	}
	c.dispatch(state.ActionEndStream{RequestID: requestID, Reason: "done"})
	c.removeActive(requestID, false)
}

func (c *ChatFlow) subscribeAll(rpc NotificationSubscriber, requestID string) []func() {
	return []func(){
		rpc.Subscribe(protocol.MethodStreamChunk, func(params any) {
			var chunk protocol.StreamChunk
			if !decodeNotification(params, &chunk) || chunk.RequestID != requestID || !c.isActive(requestID) {
				return
			}
			if chunk.Done {
				c.dispatchAuthor(requestID, authorFields{ConnectionID: chunk.AuthorConnectionID, DisplayName: chunk.AuthorDisplayName, Role: chunk.AuthorRole})
				c.dispatch(state.ActionEndStream{RequestID: requestID, Reason: nonEmpty(chunk.Reason, "done")})
				return
			}
			if chunk.Chunk != "" {
				c.dispatch(state.ActionAppendChunk{
					RequestID:          requestID,
					Chunk:              chunk.Chunk,
					AuthorConnectionID: chunk.AuthorConnectionID,
					AuthorDisplayName:  chunk.AuthorDisplayName,
					AuthorRole:         chunk.AuthorRole,
				})
			}
		}),
		rpc.Subscribe(protocol.MethodThinkingChunk, func(params any) {
			var chunk protocol.ThinkingChunk
			if !decodeNotification(params, &chunk) || chunk.RequestID != requestID || !c.isActive(requestID) || chunk.Chunk == "" {
				return
			}
			c.dispatch(state.ActionAppendThinking{
				RequestID:          requestID,
				Chunk:              chunk.Chunk,
				AuthorConnectionID: chunk.AuthorConnectionID,
				AuthorDisplayName:  chunk.AuthorDisplayName,
				AuthorRole:         chunk.AuthorRole,
			})
		}),
		rpc.Subscribe(protocol.MethodToolEvent, func(params any) {
			var event protocol.ToolEvent
			if !decodeNotification(params, &event) || event.RequestID != requestID || !c.isActive(requestID) {
				return
			}
			c.dispatch(state.ActionAppendToolCall{
				RequestID:          requestID,
				Call:               toolCallFromEvent(event),
				AuthorConnectionID: event.AuthorConnectionID,
				AuthorDisplayName:  event.AuthorDisplayName,
				AuthorRole:         event.AuthorRole,
			})
		}),
		rpc.Subscribe(protocol.MethodProgress, func(params any) {
			var progress protocol.Progress
			if !decodeNotification(params, &progress) || progress.RequestID != requestID || !c.isActive(requestID) {
				return
			}
			c.dispatch(state.ActionSetProgress{
				Progress: state.ProgressState{
					RequestID:      requestID,
					Phase:          progress.Phase,
					Message:        progress.Message,
					IterationIndex: progress.IterationIndex,
					IterationCap:   progress.IterationCap,
				},
				AuthorConnectionID: progress.AuthorConnectionID,
				AuthorDisplayName:  progress.AuthorDisplayName,
				AuthorRole:         progress.AuthorRole,
			})
		}),
	}
}

func (c *ChatFlow) dispatchAuthor(requestID string, author authorFields) {
	if author.empty() {
		return
	}
	c.dispatch(authorAction(requestID, author))
}

func (c *ChatFlow) addActive(stream *chatStream) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.active[stream.requestID] = stream
	delete(c.cancelled, stream.requestID)
}

func (c *ChatFlow) removeActive(requestID string, unsubscribe bool) *chatStream {
	c.mu.Lock()
	stream := c.active[requestID]
	delete(c.active, requestID)
	c.mu.Unlock()
	if stream != nil && unsubscribe {
		for _, unsub := range stream.unsubs {
			unsub()
		}
	}
	if stream != nil && !unsubscribe {
		for _, unsub := range stream.unsubs {
			unsub()
		}
	}
	return stream
}

func (c *ChatFlow) isActive(requestID string) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	_, ok := c.active[requestID]
	return ok
}

func (c *ChatFlow) isCancelled(requestID string) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	_, ok := c.cancelled[requestID]
	return ok
}

func (c *ChatFlow) currentRequestID() string {
	c.mu.Lock()
	defer c.mu.Unlock()
	for requestID := range c.active {
		return requestID
	}
	return ""
}

func (c *ChatFlow) dispatch(action state.Action) {
	if c.state != nil {
		c.state.Dispatch(action)
	}
}

func (c *ChatFlow) toast(text string) {
	c.dispatch(state.ActionToast{Kind: state.ToastError, Text: text, TTL: chatToastTTL})
}

func (c *ChatFlow) timeNow() time.Time {
	if c.now == nil {
		return time.Now()
	}
	return c.now()
}

func decodeNotification(src any, dst any) bool {
	switch v := src.(type) {
	case nil:
		return false
	case json.RawMessage:
		return json.Unmarshal(v, dst) == nil
	case []byte:
		return json.Unmarshal(v, dst) == nil
	case string:
		return json.Unmarshal([]byte(v), dst) == nil
	default:
		b, err := json.Marshal(v)
		if err != nil {
			return false
		}
		return json.Unmarshal(b, dst) == nil
	}
}

func toolCallFromEvent(event protocol.ToolEvent) state.ToolCall {
	call := state.ToolCall{
		EventID:     event.CallID,
		ToolCallID:  event.CallID,
		ToolName:    event.ToolName,
		ArgsPreview: compactJSON(event.ToolArgs),
	}
	switch event.EventType {
	case "tool_call_start":
		call.Status = "running"
	case "tool_error":
		call.Status = "error"
		call.Error = nonEmpty(event.Message, compactJSON(event.ToolResult))
	default:
		call.Status = "ok"
		call.ResultPreview = nonEmpty(event.Message, nonEmpty(event.Diff, compactJSON(event.ToolResult)))
	}
	return call
}

func compactJSON(v any) string {
	if v == nil {
		return ""
	}
	b, err := json.Marshal(v)
	if err != nil {
		return fmt.Sprint(v)
	}
	if string(b) == "null" {
		return ""
	}
	return string(b)
}

func newRequestID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err == nil {
		b[6] = (b[6] & 0x0f) | 0x40
		b[8] = (b[8] & 0x3f) | 0x80
		return "chat-" + hex.EncodeToString(b[:])
	}
	return fmt.Sprintf("chat-%d", time.Now().UnixNano())
}
