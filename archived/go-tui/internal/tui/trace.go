package tui

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type traceEvent struct {
	At         int64  `json:"at_ns"`
	Event      string `json:"event"`
	Msg        string `json:"msg,omitempty"`
	DurationNS int64  `json:"duration_ns,omitempty"`
	Width      int    `json:"width,omitempty"`
	Height     int    `json:"height,omitempty"`
}

var appTrace = struct {
	once sync.Once
	mu   sync.Mutex
	file *os.File
}{}

func traceStart(event, msg string) time.Time {
	if !traceReady() {
		return time.Time{}
	}
	now := time.Now()
	writeTrace(traceEvent{At: now.UnixNano(), Event: event + ".start", Msg: msg})
	return now
}

func traceDone(event string, start time.Time, width, height int) {
	if start.IsZero() || !traceReady() {
		return
	}
	now := time.Now()
	writeTrace(traceEvent{At: now.UnixNano(), Event: event + ".done", DurationNS: now.Sub(start).Nanoseconds(), Width: width, Height: height})
}

func traceReady() bool {
	appTrace.once.Do(func() {
		if os.Getenv("GOCLI_POOR_TRACE") != "1" {
			return
		}
		stateHome := os.Getenv("XDG_STATE_HOME")
		if stateHome == "" {
			if home, err := os.UserHomeDir(); err == nil && home != "" {
				stateHome = filepath.Join(home, ".local", "state")
			}
		}
		if stateHome == "" {
			return
		}
		dir := filepath.Join(stateHome, "gocli-poor")
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return
		}
		f, err := os.OpenFile(filepath.Join(dir, "trace.jsonl"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
		if err == nil {
			appTrace.file = f
		}
	})
	return appTrace.file != nil
}

func writeTrace(ev traceEvent) {
	appTrace.mu.Lock()
	defer appTrace.mu.Unlock()
	if appTrace.file == nil {
		return
	}
	b, err := json.Marshal(ev)
	if err != nil {
		return
	}
	_, _ = appTrace.file.Write(append(b, '\n'))
}
