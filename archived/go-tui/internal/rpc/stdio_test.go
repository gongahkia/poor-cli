package rpc

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sync"
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/transport"
)

type testPeer struct {
	client       *Client
	serverRead   *transport.Reader
	serverWrite  *transport.Writer
	serverPipeW  *io.PipeWriter
	serverReadIn *io.PipeReader
	clientWriteW *io.PipeWriter
}

type testEnvelope struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      *int64          `json:"id,omitempty"`
	Method  string          `json:"method,omitempty"`
	Params  json.RawMessage `json:"params,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

func newTestPeer(t *testing.T) *testPeer {
	t.Helper()
	clientPipeR, serverPipeW := io.Pipe()
	serverReadIn, clientWriteW := io.Pipe()
	p := &testPeer{
		client:       NewClient(clientPipeR, clientWriteW),
		serverRead:   transport.NewReader(serverReadIn),
		serverWrite:  transport.NewWriter(serverPipeW),
		serverPipeW:  serverPipeW,
		serverReadIn: serverReadIn,
		clientWriteW: clientWriteW,
	}
	t.Cleanup(func() {
		_ = serverPipeW.Close()
		_ = p.client.Close()
		_ = serverReadIn.Close()
		_ = clientWriteW.Close()
	})
	return p
}

func readEnvelope(r *transport.Reader) (testEnvelope, error) {
	var env testEnvelope
	body, err := r.ReadMessage()
	if err != nil {
		return env, err
	}
	return env, json.Unmarshal(body, &env)
}

func writeEnvelope(w *transport.Writer, env testEnvelope) error {
	body, err := json.Marshal(env)
	if err != nil {
		return err
	}
	return w.WriteMessage(body)
}

func rawJSON(t *testing.T, v any) json.RawMessage {
	t.Helper()
	body, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return body
}

func ptrID(id int64) *int64 { return &id }

func TestCallSuccessRoundTrip(t *testing.T) {
	p := newTestPeer(t)
	serverErr := make(chan error, 1)
	go func() {
		req, err := readEnvelope(p.serverRead)
		if err != nil {
			serverErr <- err
			return
		}
		if req.Method != "test/success" {
			serverErr <- fmt.Errorf("method = %q", req.Method)
			return
		}
		serverErr <- writeEnvelope(p.serverWrite, testEnvelope{JSONRPC: "2.0", ID: req.ID, Result: rawJSON(t, map[string]string{"value": "ok"})})
	}()
	var got struct {
		Value string `json:"value"`
	}
	if err := p.client.Call(context.Background(), "test/success", map[string]int{"n": 1}, &got); err != nil {
		t.Fatal(err)
	}
	if got.Value != "ok" {
		t.Fatalf("value = %q", got.Value)
	}
	if err := <-serverErr; err != nil {
		t.Fatal(err)
	}
}

func TestCallErrorResponse(t *testing.T) {
	p := newTestPeer(t)
	go func() {
		req, err := readEnvelope(p.serverRead)
		if err != nil {
			return
		}
		_ = writeEnvelope(p.serverWrite, testEnvelope{JSONRPC: "2.0", ID: req.ID, Error: &rpcError{Code: -32000, Message: "boom", Data: rawJSON(t, map[string]string{"error_code": "x"})}})
	}()
	err := p.client.Call(context.Background(), "test/error", nil, nil)
	var callErr *rpcError
	if !errors.As(err, &callErr) {
		t.Fatalf("err = %v", err)
	}
	if callErr.Code != -32000 || callErr.Message != "boom" || string(callErr.Data) != `{"error_code":"x"}` {
		t.Fatalf("callErr = %#v data=%s", callErr, callErr.Data)
	}
}

func TestCallContextCancellationReleasesPending(t *testing.T) {
	p := newTestPeer(t)
	readDone := make(chan error, 1)
	go func() {
		_, err := readEnvelope(p.serverRead)
		readDone <- err
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	err := p.client.Call(ctx, "test/cancel", nil, nil)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("err = %v", err)
	}
	if err := <-readDone; err != nil {
		t.Fatal(err)
	}
	if n := pendingLen(p.client); n != 0 {
		t.Fatalf("pending len = %d", n)
	}
}

func TestConcurrentCallsOutOfOrderResponses(t *testing.T) {
	p := newTestPeer(t)
	const n = 10
	serverErr := make(chan error, 1)
	go func() {
		reqs := make([]testEnvelope, 0, n)
		for range n {
			req, err := readEnvelope(p.serverRead)
			if err != nil {
				serverErr <- err
				return
			}
			reqs = append(reqs, req)
		}
		for i := len(reqs) - 1; i >= 0; i-- {
			var params struct {
				I int `json:"i"`
			}
			if err := json.Unmarshal(reqs[i].Params, &params); err != nil {
				serverErr <- err
				return
			}
			if err := writeEnvelope(p.serverWrite, testEnvelope{JSONRPC: "2.0", ID: reqs[i].ID, Result: rawJSON(t, params)}); err != nil {
				serverErr <- err
				return
			}
		}
		serverErr <- nil
	}()
	errs := make(chan error, n)
	var wg sync.WaitGroup
	for i := range n {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			var got struct {
				I int `json:"i"`
			}
			err := p.client.Call(context.Background(), fmt.Sprintf("test/%d", i), map[string]int{"i": i}, &got)
			if err != nil {
				errs <- err
				return
			}
			if got.I != i {
				errs <- fmt.Errorf("got %d want %d", got.I, i)
			}
		}(i)
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatal(err)
		}
	}
	if err := <-serverErr; err != nil {
		t.Fatal(err)
	}
}

func TestNotificationsRouteToSubscribers(t *testing.T) {
	p := newTestPeer(t)
	ch1 := make(chan any, 1)
	ch2 := make(chan any, 1)
	unsub := p.client.Subscribe("test/notify", func(params any) { ch1 <- params })
	p.client.Subscribe("test/notify", func(params any) { ch2 <- params })
	if err := writeEnvelope(p.serverWrite, testEnvelope{JSONRPC: "2.0", Method: "test/notify", Params: rawJSON(t, map[string]string{"value": "ok"})}); err != nil {
		t.Fatal(err)
	}
	assertNotifyValue(t, <-ch1)
	assertNotifyValue(t, <-ch2)
	unsub()
	if err := writeEnvelope(p.serverWrite, testEnvelope{JSONRPC: "2.0", Method: "test/notify", Params: rawJSON(t, map[string]string{"value": "again"})}); err != nil {
		t.Fatal(err)
	}
	select {
	case <-ch1:
		t.Fatal("unsubscribed handler received notification")
	case <-time.After(30 * time.Millisecond):
	}
	assertNotifyValue(t, <-ch2)
}

func TestTransportEOFReleasesPending(t *testing.T) {
	p := newTestPeer(t)
	errs := make(chan error, 1)
	go func() {
		errs <- p.client.Call(context.Background(), "test/pending", nil, nil)
	}()
	if _, err := readEnvelope(p.serverRead); err != nil {
		t.Fatal(err)
	}
	_ = p.serverPipeW.Close()
	select {
	case err := <-errs:
		if err == nil {
			t.Fatal("expected error")
		}
	case <-time.After(time.Second):
		t.Fatal("call did not unblock")
	}
}

func assertNotifyValue(t *testing.T, got any) {
	t.Helper()
	m, ok := got.(map[string]any)
	if !ok {
		t.Fatalf("params = %#v", got)
	}
	if m["value"] == "" {
		t.Fatalf("params = %#v", got)
	}
}

func pendingLen(c *Client) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.pending)
}
