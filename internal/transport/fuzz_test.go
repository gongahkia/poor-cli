package transport

import (
	"bytes"
	"fmt"
	"testing"
)

func FuzzTransportReader(f *testing.F) {
	seeds := []struct {
		header []byte
		body   []byte
	}{
		{[]byte("Content-Length: 2\r\n\r\n"), []byte("{}")},
		{[]byte("Content-Length: 0\n\n"), nil},
		{[]byte("content-length: 5\r\n\r\n"), []byte("hello")},
		{[]byte("Content-Length: -1\r\n\r\n"), nil},
		{[]byte("x: y\r\n\r\n"), []byte("{}")},
	}
	for _, seed := range seeds {
		f.Add(seed.header, seed.body)
	}
	f.Fuzz(func(t *testing.T, header, body []byte) {
		if len(header) > headerLimit+1024 {
			header = header[:headerLimit+1024]
		}
		if len(body) > 1<<20 {
			body = body[:1<<20]
		}
		input := append(append([]byte(nil), header...), body...)
		defer func() {
			if r := recover(); r != nil {
				t.Fatalf("ReadMessage panic: %v header=%q body_len=%d", r, header, len(body))
			}
		}()
		_, _ = NewReader(bytes.NewReader(input)).ReadMessage()
	})
}

func FuzzTransportRoundTrip(f *testing.F) {
	for _, seed := range [][]byte{nil, []byte("{}"), []byte("hello"), bytes.Repeat([]byte("x"), 4096)} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, body []byte) {
		if len(body) > 1<<20 {
			body = body[:1<<20]
		}
		var frame bytes.Buffer
		if err := NewWriter(&frame).WriteMessage(body); err != nil {
			t.Fatalf("WriteMessage: %v", err)
		}
		got, err := NewReader(&frame).ReadMessage()
		if err != nil {
			t.Fatalf("ReadMessage: %v", err)
		}
		if !bytes.Equal(got, body) {
			t.Fatalf("roundtrip mismatch: %s", fmt.Sprintf("%x != %x", got, body))
		}
	})
}
