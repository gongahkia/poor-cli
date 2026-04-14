package transport

import (
	"bytes"
	"fmt"
	"io"
	"strconv"
	"sync"
)

const (
	headerLimit = 64 * 1024
	bodyLimit   = 128 * 1024 * 1024
	readSize    = 32 * 1024
)

var (
	crlfSep       = []byte("\r\n\r\n")
	lfSep         = []byte("\n\n")
	headerSep     = []byte(":")
	contentLength = []byte("Content-Length")
)

type Reader struct {
	src     io.Reader
	buf     []byte
	off     int
	scratch [readSize]byte
}

func NewReader(r io.Reader) *Reader {
	return &Reader{src: r}
}

func (r *Reader) ReadMessage() ([]byte, error) {
	r.compact()
	headerStart, bodyStart, err := r.readHeader()
	if err != nil {
		return nil, err
	}

	window := r.buf[r.off:]
	n, err := parseContentLength(window[:headerStart])
	if err != nil {
		return nil, err
	}
	if n > bodyLimit {
		return nil, fmt.Errorf("transport: Content-Length exceeds 128 MB")
	}

	bodyEnd := bodyStart + n
	for len(r.buf[r.off:]) < bodyEnd {
		if err := r.readMore(ErrIncompleteBody); err != nil {
			return nil, err
		}
	}

	body := r.buf[r.off+bodyStart : r.off+bodyEnd]
	r.off += bodyEnd
	return body, nil
}

func (r *Reader) readHeader() (int, int, error) {
	for {
		window := r.buf[r.off:]
		headerEnd, sepLen := findHeaderEnd(window)
		if sepLen != 0 {
			if headerEnd > headerLimit {
				return 0, 0, ErrHeaderTooLarge
			}
			return headerEnd, headerEnd + sepLen, nil
		}
		if len(window) > headerLimit {
			return 0, 0, ErrHeaderTooLarge
		}
		if err := r.readMore(ErrIncompleteHeader); err != nil {
			return 0, 0, err
		}
	}
}

func (r *Reader) compact() {
	if r.off == 0 {
		return
	}
	if r.off == len(r.buf) {
		r.buf = r.buf[:0]
		r.off = 0
		return
	}
	if r.off < 4096 || r.off < len(r.buf)/2 {
		return
	}
	n := copy(r.buf, r.buf[r.off:])
	r.buf = r.buf[:n]
	r.off = 0
}

func (r *Reader) readMore(eofErr error) error {
	n, err := r.src.Read(r.scratch[:])
	if n > 0 {
		r.buf = append(r.buf, r.scratch[:n]...)
	}
	if err == nil || n > 0 {
		return nil
	}
	if err == io.EOF {
		return eofErr
	}
	return err
}

func findHeaderEnd(b []byte) (int, int) {
	crlf := bytes.Index(b, crlfSep)
	lf := bytes.Index(b, lfSep)
	switch {
	case crlf >= 0 && (lf < 0 || crlf < lf):
		return crlf, len(crlfSep)
	case lf >= 0:
		return lf, len(lfSep)
	default:
		return 0, 0
	}
}

func parseContentLength(header []byte) (int, error) {
	for len(header) > 0 {
		line := header
		if i := bytes.IndexByte(header, '\n'); i >= 0 {
			line = header[:i]
			header = header[i+1:]
		} else {
			header = nil
		}
		line = bytes.TrimSpace(line)
		if len(line) == 0 {
			continue
		}
		name, value, ok := bytes.Cut(line, headerSep)
		if !ok || !bytes.EqualFold(bytes.TrimSpace(name), contentLength) {
			continue
		}
		n, err := parseLength(bytes.TrimSpace(value))
		if err != nil {
			return 0, err
		}
		return n, nil
	}
	return 0, ErrMissingContentLength
}

func parseLength(value []byte) (int, error) {
	if len(value) == 0 {
		return 0, fmt.Errorf("transport: invalid Content-Length")
	}
	if value[0] == '-' {
		return 0, ErrNegativeLength
	}

	var n int
	for _, c := range value {
		if c < '0' || c > '9' {
			return 0, fmt.Errorf("transport: invalid Content-Length")
		}
		next := n*10 + int(c-'0')
		if next < n {
			return 0, fmt.Errorf("transport: invalid Content-Length")
		}
		n = next
	}
	return n, nil
}

type Writer struct {
	dst io.Writer
	mu  sync.Mutex
	buf bytes.Buffer
}

func NewWriter(w io.Writer) *Writer {
	return &Writer{dst: w}
}

func (w *Writer) WriteMessage(body []byte) error {
	if len(body) > bodyLimit {
		return fmt.Errorf("transport: body exceeds 128 MB")
	}

	w.mu.Lock()
	defer w.mu.Unlock()

	w.buf.Reset()
	w.buf.Grow(len("Content-Length: \r\n\r\n") + decimalLen(len(body)) + len(body))
	_, _ = w.buf.WriteString("Content-Length: ")
	var lenBuf [20]byte
	_, _ = w.buf.Write(strconv.AppendInt(lenBuf[:0], int64(len(body)), 10))
	_, _ = w.buf.WriteString("\r\n\r\n")
	_, _ = w.buf.Write(body)
	n, err := w.dst.Write(w.buf.Bytes())
	if err == nil && n != w.buf.Len() {
		return io.ErrShortWrite
	}
	return err
}

func decimalLen(n int) int {
	if n == 0 {
		return 1
	}
	digits := 0
	for n > 0 {
		digits++
		n /= 10
	}
	return digits
}
