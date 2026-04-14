package transport

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"sort"
	"sync"
	"testing"
)

func TestRoundTrip(t *testing.T) {
	sizes := []int{1, 2, 3, 4, 8, 16, 32, 64, 100, 256, 512, 1024, 2048, 4096, 8192, 10 * 1024, 32 * 1024, 100 * 1024, 512 * 1024, 1024 * 1024}
	pr, pw := io.Pipe()
	reader := NewReader(pr)
	writer := NewWriter(pw)

	writeErr := make(chan error, 1)
	go func() {
		defer pw.Close()
		for _, size := range sizes {
			if err := writer.WriteMessage(payload(size)); err != nil {
				writeErr <- err
				return
			}
		}
		writeErr <- nil
	}()

	for _, size := range sizes {
		got, err := reader.ReadMessage()
		if err != nil {
			t.Fatalf("ReadMessage(%d): %v", size, err)
		}
		want := payload(size)
		if !bytes.Equal(got, want) {
			t.Fatalf("payload %d mismatch", size)
		}
	}
	if err := <-writeErr; err != nil {
		t.Fatalf("WriteMessage: %v", err)
	}
}

func TestHeaderSeparators(t *testing.T) {
	tests := []struct {
		name string
		in   string
	}{
		{"crlf", "Content-Length: 7\r\n\r\n{\"a\":1}"},
		{"lf", "Content-Length: 7\n\n{\"a\":1}"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := NewReader(stringsReader(tt.in)).ReadMessage()
			if err != nil {
				t.Fatalf("ReadMessage: %v", err)
			}
			if string(got) != "{\"a\":1}" {
				t.Fatalf("body = %q", got)
			}
		})
	}
}

func TestPipelinedMessages(t *testing.T) {
	var buf bytes.Buffer
	writer := NewWriter(&buf)
	want := [][]byte{[]byte(`{"n":1}`), []byte(`{"n":2}`), []byte(`{"n":3}`)}
	for _, msg := range want {
		if err := writer.WriteMessage(msg); err != nil {
			t.Fatalf("WriteMessage: %v", err)
		}
	}
	reader := NewReader(&buf)
	for i, msg := range want {
		got, err := reader.ReadMessage()
		if err != nil {
			t.Fatalf("ReadMessage(%d): %v", i, err)
		}
		if !bytes.Equal(got, msg) {
			t.Fatalf("message %d = %q, want %q", i, got, msg)
		}
	}
}

func TestUTF8ByteLength(t *testing.T) {
	body := []byte(`{"text":"λ"}`)
	var buf bytes.Buffer
	if err := NewWriter(&buf).WriteMessage(body); err != nil {
		t.Fatalf("WriteMessage: %v", err)
	}
	if !bytes.HasPrefix(buf.Bytes(), []byte("Content-Length: 13\r\n\r\n")) {
		t.Fatalf("header = %q", buf.Bytes()[:bytes.Index(buf.Bytes(), []byte("\r\n\r\n"))+4])
	}
	got, err := NewReader(&buf).ReadMessage()
	if err != nil {
		t.Fatalf("ReadMessage: %v", err)
	}
	if !bytes.Equal(got, body) {
		t.Fatalf("body = %q, want %q", got, body)
	}
}

func TestPartialReads(t *testing.T) {
	reader := NewReader(slowReader{r: stringsReader("Content-Length: 7\r\n\r\n{\"a\":1}")})
	got, err := reader.ReadMessage()
	if err != nil {
		t.Fatalf("ReadMessage: %v", err)
	}
	if string(got) != "{\"a\":1}" {
		t.Fatalf("body = %q", got)
	}
}

func TestMalformedHeaders(t *testing.T) {
	tests := []struct {
		name string
		in   string
		err  error
	}{
		{"missing", "Content-Type: application/json\r\n\r\n{}", ErrMissingContentLength},
		{"negative", "Content-Length: -1\r\n\r\n{}", ErrNegativeLength},
		{"non-integer", "Content-Length: no\r\n\r\n{}", nil},
		{"extra-field-missing", "Content-Type: application/json\r\nX-Test: y\r\n\r\n{}", ErrMissingContentLength},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := NewReader(stringsReader(tt.in)).ReadMessage()
			if err == nil {
				t.Fatal("ReadMessage nil error")
			}
			if tt.err != nil && !errors.Is(err, tt.err) {
				t.Fatalf("error = %v, want %v", err, tt.err)
			}
		})
	}
}

func TestIncompleteHeader(t *testing.T) {
	_, err := NewReader(stringsReader("Content-Length: 7\r\n")).ReadMessage()
	if !errors.Is(err, ErrIncompleteHeader) {
		t.Fatalf("error = %v, want %v", err, ErrIncompleteHeader)
	}
}

func TestHeaderTooLarge(t *testing.T) {
	var buf bytes.Buffer
	buf.WriteString("X-A: ")
	buf.Write(bytes.Repeat([]byte("x"), headerLimit+1))
	buf.WriteString("\r\n\r\n")
	_, err := NewReader(&buf).ReadMessage()
	if !errors.Is(err, ErrHeaderTooLarge) {
		t.Fatalf("error = %v, want %v", err, ErrHeaderTooLarge)
	}
}

func TestTruncatedBody(t *testing.T) {
	_, err := NewReader(stringsReader("Content-Length: 8\r\n\r\n{\"a\":1}")).ReadMessage()
	if !errors.Is(err, ErrIncompleteBody) {
		t.Fatalf("error = %v, want %v", err, ErrIncompleteBody)
	}
}

func TestConcurrentWritersAreSerialized(t *testing.T) {
	var buf lockedBuffer
	writer := NewWriter(&buf)
	const n = 100

	var wg sync.WaitGroup
	for i := range n {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			body := []byte(fmt.Sprintf(`{"i":%03d}`, i))
			if err := writer.WriteMessage(body); err != nil {
				t.Errorf("WriteMessage(%d): %v", i, err)
			}
		}(i)
	}
	wg.Wait()

	reader := NewReader(bytes.NewReader(buf.Bytes()))
	got := make([]string, 0, n)
	for range n {
		body, err := reader.ReadMessage()
		if err != nil {
			t.Fatalf("ReadMessage: %v", err)
		}
		got = append(got, string(body))
	}
	sort.Strings(got)
	for i := range n {
		want := fmt.Sprintf(`{"i":%03d}`, i)
		if got[i] != want {
			t.Fatalf("got[%d] = %q, want %q", i, got[i], want)
		}
	}
}

func payload(size int) []byte {
	p := make([]byte, size)
	for i := range p {
		p[i] = byte('a' + i%26)
	}
	return p
}

type slowReader struct {
	r io.Reader
}

func (s slowReader) Read(p []byte) (int, error) {
	if len(p) > 1 {
		p = p[:1]
	}
	return s.r.Read(p)
}

type lockedBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (b *lockedBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.Write(p)
}

func (b *lockedBuffer) Bytes() []byte {
	b.mu.Lock()
	defer b.mu.Unlock()
	out := make([]byte, b.buf.Len())
	copy(out, b.buf.Bytes())
	return out
}

func stringsReader(s string) *bytes.Reader {
	return bytes.NewReader([]byte(s))
}
