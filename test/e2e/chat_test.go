//go:build e2e

package e2e

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/server"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/transport"
	"github.com/gongahkia/gocli-poor/internal/tui"
	"github.com/gongahkia/gocli-poor/internal/tui/flows"
)

const (
	e2eTimeout = 30 * time.Second
	e2eWidth   = 80
	e2eHeight  = 12
)

func TestE2E_HappyPathChat(t *testing.T) {
	if testing.Short() {
		t.Skip("e2e")
	}
	serverPath := os.Getenv("GOCLI_POOR_E2E_SERVER")
	if serverPath == "" {
		t.Skip("set GOCLI_POOR_E2E_SERVER")
	}
	model := getenvDefault("GOCLI_POOR_E2E_MODEL", "llama3.1")
	ctx, cancel := context.WithTimeout(context.Background(), e2eTimeout)
	defer cancel()

	mgr := server.NewManager(server.Config{
		BinaryPath:      serverPath,
		Cwd:             t.TempDir(),
		ReadyTimeout:    5 * time.Second,
		ShutdownTimeout: 2 * time.Second,
		Env: map[string]string{
			"POOR_CLI_SERVER_LOG_FILE": filepath.Join(t.TempDir(), "poor-cli-server.log"),
		},
	})
	if err := mgr.Start(ctx); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = mgr.Shutdown(context.Background()) })

	rpc := newRPCClient(mgr.Stdout(), mgr.Stdin())
	defer rpc.Close()
	initServer(t, ctx, rpc, model)

	rendered := runRenderedChat(t, rpc, "say hi. Reply with exactly: hello", "hello")
	if !strings.Contains(strings.ToLower(rendered), "hello") {
		t.Fatalf("rendered output missing hello:\n%s", rendered)
	}
}

func TestE2E_FixtureReplay(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), e2eTimeout)
	defer cancel()
	frames := loadFixture(t, "chat-session-01.jsonl")
	rpc, wait := startFixtureRPC(t, frames)
	defer rpc.Close()
	initServer(t, ctx, rpc, "llama3.1")

	rendered := runRenderedChat(t, rpc, "say hi", "hello from fixture")
	golden := readFixture(t, "chat-session-01.golden.txt")
	if rendered != strings.TrimRight(golden, "\n") {
		t.Fatalf("rendered output mismatch\nwant:\n%s\n\ngot:\n%s", golden, rendered)
	}
	if err := wait(); err != nil {
		t.Fatal(err)
	}
}

func initServer(t *testing.T, ctx context.Context, rpc *rpcClient, model string) {
	t.Helper()
	streaming := true
	var result protocol.InitializeResult
	err := rpc.Call(ctx, protocol.MethodInitialize, protocol.InitializeParams{
		Provider:  "ollama",
		Model:     model,
		Streaming: &streaming,
	}, &result)
	if err != nil {
		t.Fatal(err)
	}
	if !result.Capabilities.ChatStreamingProvider {
		t.Fatalf("server lacks chat streaming: %#v", result.Capabilities)
	}
}

func runRenderedChat(t *testing.T, rpc *rpcClient, prompt, want string) string {
	t.Helper()
	model := tui.NewModel(&state.AppState{
		Connection: state.ConnState{Phase: state.Ready},
		Provider:   state.ProviderState{Name: "ollama", Model: "llama3.1"},
	}, tui.WithRPCClient(rpc), tui.WithIntroVersion("e2e"))
	next, _ := model.Update(tui.IntroDoneMsg{})
	model = next.(tui.Model)
	next, _ = model.Update(tui.ResizeMsg{Width: e2eWidth, Height: e2eHeight})
	model = next.(tui.Model)
	next, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(prompt)})
	model = next.(tui.Model)
	next, cmd := model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	model = next.(tui.Model)
	if cmd == nil {
		t.Fatal("submit command missing")
	}
	next, _ = model.Update(cmd())
	model = next.(tui.Model)

	deadline := time.Now().Add(e2eTimeout - 2*time.Second)
	for time.Now().Before(deadline) {
		st := model.Store.Snapshot()
		if assistantContains(st.Messages, want) && st.InFlight == nil {
			model.State = &st
			model.Chat.SetMessages(st.Messages)
			return normalizeRendered(model.View())
		}
		time.Sleep(20 * time.Millisecond)
	}
	st := model.Store.Snapshot()
	model.State = &st
	model.Chat.SetMessages(st.Messages)
	t.Fatalf("chat did not render %q before timeout:\n%s", want, normalizeRendered(model.View()))
	return ""
}

func assistantContains(messages []state.Message, want string) bool {
	want = strings.ToLower(want)
	for _, msg := range messages {
		if msg.Role == state.RoleAssistant && strings.Contains(strings.ToLower(msg.Content), want) {
			return true
		}
	}
	return false
}

type rpcClient struct {
	reader *transport.Reader
	writer *transport.Writer

	mu      sync.Mutex
	nextID  int64
	pending map[string]chan rpcResponse
	subs    map[string][]subscription
	subID   uint64
	closed  bool
	done    chan struct{}
	err     error
}

type subscription struct {
	id      uint64
	handler flows.NotificationHandler
}

type rpcResponse struct {
	result json.RawMessage
	err    *rpcError
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type rpcEnvelope struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method,omitempty"`
	Params  json.RawMessage `json:"params,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

func newRPCClient(r io.Reader, w io.Writer) *rpcClient {
	c := &rpcClient{
		reader:  transport.NewReader(r),
		writer:  transport.NewWriter(w),
		pending: map[string]chan rpcResponse{},
		subs:    map[string][]subscription{},
		done:    make(chan struct{}),
	}
	go c.readLoop()
	return c
}

func (c *rpcClient) Call(ctx context.Context, method string, params any, result any) error {
	id := c.reserveID()
	ch := make(chan rpcResponse, 1)
	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		return io.ErrClosedPipe
	}
	c.pending[strconv.FormatInt(id, 10)] = ch
	c.mu.Unlock()

	req := map[string]any{"jsonrpc": "2.0", "id": id, "method": method}
	if params != nil {
		req["params"] = params
	}
	body, err := json.Marshal(req)
	if err != nil {
		return err
	}
	if err := c.writer.WriteMessage(body); err != nil {
		c.dropPending(id)
		return err
	}
	select {
	case resp := <-ch:
		if resp.err != nil {
			return fmt.Errorf("rpc %s: %s", method, resp.err.Message)
		}
		if result == nil || len(resp.result) == 0 {
			return nil
		}
		return json.Unmarshal(resp.result, result)
	case <-ctx.Done():
		c.dropPending(id)
		return ctx.Err()
	case <-c.done:
		c.dropPending(id)
		if c.err != nil {
			return c.err
		}
		return io.ErrClosedPipe
	}
}

func (c *rpcClient) Notify(ctx context.Context, method string, params any) error {
	req := map[string]any{"jsonrpc": "2.0", "method": method}
	if params != nil {
		req["params"] = params
	}
	body, err := json.Marshal(req)
	if err != nil {
		return err
	}
	done := make(chan error, 1)
	go func() { done <- c.writer.WriteMessage(body) }()
	select {
	case err := <-done:
		return err
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (c *rpcClient) Subscribe(method string, handler flows.NotificationHandler) func() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.subID++
	id := c.subID
	c.subs[method] = append(c.subs[method], subscription{id: id, handler: handler})
	return func() {
		c.mu.Lock()
		defer c.mu.Unlock()
		subs := c.subs[method]
		for i, sub := range subs {
			if sub.id == id {
				c.subs[method] = append(subs[:i], subs[i+1:]...)
				break
			}
		}
	}
}

func (c *rpcClient) Close() {
	c.mu.Lock()
	c.closeLocked(nil)
	c.mu.Unlock()
}

func (c *rpcClient) reserveID() int64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.nextID++
	return c.nextID
}

func (c *rpcClient) dropPending(id int64) {
	c.mu.Lock()
	delete(c.pending, strconv.FormatInt(id, 10))
	c.mu.Unlock()
}

func (c *rpcClient) readLoop() {
	for {
		body, err := c.reader.ReadMessage()
		if err != nil {
			c.mu.Lock()
			c.closeLocked(err)
			c.mu.Unlock()
			return
		}
		var msg rpcEnvelope
		if err := json.Unmarshal(body, &msg); err != nil {
			c.mu.Lock()
			c.closeLocked(err)
			c.mu.Unlock()
			return
		}
		if msg.Method != "" && len(msg.ID) == 0 {
			c.dispatch(msg.Method, msg.Params)
			continue
		}
		key := string(msg.ID)
		c.mu.Lock()
		ch := c.pending[key]
		delete(c.pending, key)
		c.mu.Unlock()
		if ch != nil {
			ch <- rpcResponse{result: msg.Result, err: msg.Error}
		}
	}
}

func (c *rpcClient) dispatch(method string, params json.RawMessage) {
	c.mu.Lock()
	subs := append([]subscription(nil), c.subs[method]...)
	c.mu.Unlock()
	for _, sub := range subs {
		sub.handler(params)
	}
}

func (c *rpcClient) closeLocked(err error) {
	if c.closed {
		return
	}
	c.closed = true
	c.err = err
	for key, ch := range c.pending {
		delete(c.pending, key)
		close(ch)
	}
	close(c.done)
}

type fixtureFrame struct {
	Dir  string          `json:"dir"`
	Body json.RawMessage `json:"body"`
}

func startFixtureRPC(t *testing.T, frames []fixtureFrame) (*rpcClient, func() error) {
	t.Helper()
	serverInR, clientOutW := io.Pipe()
	clientInR, serverOutW := io.Pipe()
	errCh := make(chan error, 1)
	go func() {
		defer serverInR.Close()
		defer serverOutW.Close()
		errCh <- serveFixture(frames, serverInR, serverOutW)
	}()
	t.Cleanup(func() {
		_ = clientOutW.Close()
		_ = clientInR.Close()
	})
	return newRPCClient(clientInR, clientOutW), func() error {
		select {
		case err := <-errCh:
			return err
		case <-time.After(time.Second):
			return errors.New("fixture server did not finish")
		}
	}
}

func serveFixture(frames []fixtureFrame, r io.Reader, w io.Writer) error {
	reader := transport.NewReader(r)
	writer := transport.NewWriter(w)
	var lastID json.RawMessage
	var requestID string
	for _, frame := range frames {
		switch frame.Dir {
		case "c2s":
			body, err := reader.ReadMessage()
			if err != nil {
				return err
			}
			var actual rpcEnvelope
			if err := json.Unmarshal(body, &actual); err != nil {
				return err
			}
			var expected rpcEnvelope
			if err := json.Unmarshal(frame.Body, &expected); err != nil {
				return err
			}
			if actual.Method != expected.Method {
				return fmt.Errorf("fixture method mismatch: got %s want %s", actual.Method, expected.Method)
			}
			lastID = append(lastID[:0], actual.ID...)
			if actual.Method == protocol.MethodChatStreaming {
				var params protocol.ChatStreamingParams
				_ = json.Unmarshal(actual.Params, &params)
				requestID = params.RequestID
			}
		case "s2c":
			body, err := adaptFixtureBody(frame.Body, lastID, requestID)
			if err != nil {
				return err
			}
			if err := writer.WriteMessage(body); err != nil {
				return err
			}
		default:
			return fmt.Errorf("bad fixture dir %q", frame.Dir)
		}
	}
	return nil
}

func adaptFixtureBody(raw json.RawMessage, id json.RawMessage, requestID string) ([]byte, error) {
	var msg map[string]any
	if err := json.Unmarshal(raw, &msg); err != nil {
		return nil, err
	}
	if _, ok := msg["id"]; ok && len(id) > 0 {
		var parsed any
		if err := json.Unmarshal(id, &parsed); err != nil {
			return nil, err
		}
		msg["id"] = parsed
	}
	if params, ok := msg["params"].(map[string]any); ok && requestID != "" {
		if _, has := params["requestId"]; has {
			params["requestId"] = requestID
		}
	}
	return json.Marshal(msg)
}

func loadFixture(t *testing.T, name string) []fixtureFrame {
	t.Helper()
	file, err := os.Open(fixturePath(t, name))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	var frames []fixtureFrame
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var frame fixtureFrame
		if err := json.Unmarshal([]byte(line), &frame); err != nil {
			t.Fatal(err)
		}
		frames = append(frames, frame)
	}
	if err := scanner.Err(); err != nil {
		t.Fatal(err)
	}
	return frames
}

func readFixture(t *testing.T, name string) string {
	t.Helper()
	body, err := os.ReadFile(fixturePath(t, name))
	if err != nil {
		t.Fatal(err)
	}
	return string(body)
}

func fixturePath(t *testing.T, name string) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(file), "..", "fixtures", name)
}

var ansiRE = regexp.MustCompile(`\x1b\[[0-?]*[ -/]*[@-~]`)

func normalizeRendered(s string) string {
	s = ansiRE.ReplaceAllString(s, "")
	s = strings.ReplaceAll(s, "\r\n", "\n")
	lines := strings.Split(s, "\n")
	for i := range lines {
		lines[i] = strings.TrimRight(lines[i], " \t")
	}
	return strings.TrimRight(strings.Join(lines, "\n"), "\n")
}

func getenvDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
