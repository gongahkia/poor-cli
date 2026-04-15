package rpc

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"reflect"
	"sync"
	"sync/atomic"

	"github.com/gongahkia/gocli-poor/internal/transport"
	"github.com/gongahkia/gocli-poor/internal/tui/flows"
)

type Client struct {
	reader *transport.Reader
	writer *transport.Writer

	nextID   atomic.Int64
	mu       sync.Mutex
	pending  map[int64]chan response
	handlers map[string][]flows.NotificationHandler
	closed   bool
	done     chan struct{}
}

type request struct {
	JSONRPC string `json:"jsonrpc"`
	ID      int64  `json:"id,omitempty"`
	Method  string `json:"method"`
	Params  any    `json:"params,omitempty"`
}

type wireMessage struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      *int64          `json:"id,omitempty"`
	Method  string          `json:"method,omitempty"`
	Params  json.RawMessage `json:"params,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data,omitempty"`
}

type response struct {
	msg wireMessage
	err error
}

func NewClient(stdout io.Reader, stdin io.Writer) *Client {
	c := &Client{
		reader:   transport.NewReader(stdout),
		writer:   transport.NewWriter(stdin),
		pending:  map[int64]chan response{},
		handlers: map[string][]flows.NotificationHandler{},
		done:     make(chan struct{}),
	}
	go c.readLoop()
	return c
}

func (c *Client) Call(ctx context.Context, method string, params any, result any) error {
	if ctx == nil {
		ctx = context.Background()
	}
	id := c.nextID.Add(1)
	ch := make(chan response, 1)
	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		return errors.New("rpc: client closed")
	}
	c.pending[id] = ch
	c.mu.Unlock()
	if err := c.write(request{JSONRPC: "2.0", ID: id, Method: method, Params: params}); err != nil {
		c.removePending(id)
		return err
	}
	select {
	case res := <-ch:
		if res.err != nil {
			return res.err
		}
		if res.msg.Error != nil {
			return res.msg.Error
		}
		if result == nil || len(res.msg.Result) == 0 {
			return nil
		}
		return json.Unmarshal(res.msg.Result, result)
	case <-ctx.Done():
		c.removePending(id)
		return ctx.Err()
	}
}

func (c *Client) Notify(ctx context.Context, method string, params any) error {
	if ctx == nil {
		ctx = context.Background()
	}
	done := make(chan error, 1)
	go func() { done <- c.write(request{JSONRPC: "2.0", Method: method, Params: params}) }()
	select {
	case err := <-done:
		return err
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (c *Client) Subscribe(method string, handler flows.NotificationHandler) func() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.handlers[method] = append(c.handlers[method], handler)
	return func() {
		c.mu.Lock()
		defer c.mu.Unlock()
		handlers := c.handlers[method]
		target := reflect.ValueOf(handler).Pointer()
		for i, h := range handlers {
			if reflect.ValueOf(h).Pointer() == target {
				c.handlers[method] = append(handlers[:i], handlers[i+1:]...)
				break
			}
		}
	}
}

func (c *Client) Close() error {
	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		return nil
	}
	c.closed = true
	for id, ch := range c.pending {
		delete(c.pending, id)
		ch <- response{err: errors.New("rpc: client closed")}
	}
	c.mu.Unlock()
	<-c.done
	return nil
}

func (c *Client) write(req request) error {
	body, err := json.Marshal(req)
	if err != nil {
		return err
	}
	return c.writer.WriteMessage(body)
}

func (c *Client) readLoop() {
	defer close(c.done)
	for {
		body, err := c.reader.ReadMessage()
		if err != nil {
			c.closeWithError(err)
			return
		}
		var msg wireMessage
		if err := json.Unmarshal(body, &msg); err != nil {
			continue
		}
		if msg.ID != nil {
			c.deliverResponse(*msg.ID, response{msg: msg})
			continue
		}
		if msg.Method != "" {
			c.deliverNotification(msg)
		}
	}
}

func (c *Client) deliverResponse(id int64, res response) {
	c.mu.Lock()
	ch := c.pending[id]
	delete(c.pending, id)
	c.mu.Unlock()
	if ch != nil {
		ch <- res
	}
}

func (c *Client) deliverNotification(msg wireMessage) {
	var params any
	if len(msg.Params) > 0 {
		_ = json.Unmarshal(msg.Params, &params)
	}
	c.mu.Lock()
	handlers := append([]flows.NotificationHandler(nil), c.handlers[msg.Method]...)
	c.mu.Unlock()
	for _, handler := range handlers {
		handler(params)
	}
}

func (c *Client) closeWithError(err error) {
	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		return
	}
	c.closed = true
	for id, ch := range c.pending {
		delete(c.pending, id)
		ch <- response{err: err}
	}
	c.mu.Unlock()
}

func (c *Client) removePending(id int64) {
	c.mu.Lock()
	delete(c.pending, id)
	c.mu.Unlock()
}

func (e *rpcError) Error() string {
	if e == nil {
		return ""
	}
	return fmt.Sprintf("rpc %d: %s", e.Code, e.Message)
}
