package transport

import (
	"bytes"
	"testing"
)

func BenchmarkWriter_1KB(b *testing.B) {
	benchmarkWriter(b, 1024)
}

func BenchmarkWriter_100KB(b *testing.B) {
	benchmarkWriter(b, 100*1024)
}

func BenchmarkReader_1KB(b *testing.B) {
	benchmarkReader(b, 1024)
}

func BenchmarkReader_100KB(b *testing.B) {
	benchmarkReader(b, 100*1024)
}

func benchmarkWriter(b *testing.B, size int) {
	body := payload(size)
	dst := discardWriter{}
	writer := NewWriter(dst)
	b.SetBytes(int64(size))
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		if err := writer.WriteMessage(body); err != nil {
			b.Fatal(err)
		}
	}
}

func benchmarkReader(b *testing.B, size int) {
	body := payload(size)
	var frame bytes.Buffer
	if err := NewWriter(&frame).WriteMessage(body); err != nil {
		b.Fatal(err)
	}
	data := frame.Bytes()
	src := bytes.NewReader(data)
	reader := NewReader(src)
	b.SetBytes(int64(size))
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		src.Reset(data)
		reader.buf = reader.buf[:0]
		reader.off = 0
		got, err := reader.ReadMessage()
		if err != nil {
			b.Fatal(err)
		}
		if len(got) != size {
			b.Fatalf("len = %d, want %d", len(got), size)
		}
	}
}

type discardWriter struct{}

func (discardWriter) Write(p []byte) (int, error) {
	return len(p), nil
}
