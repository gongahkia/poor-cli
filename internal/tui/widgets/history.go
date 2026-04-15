package widgets

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
)

const defaultHistoryMax = 500

type History struct {
	entries []string
	cursor  int
	path    string
	max     int
}

func NewHistory(path string, max int) *History {
	if max <= 0 {
		max = defaultHistoryMax
	}
	h := &History{path: expandPath(path), max: max, cursor: -1}
	h.load()
	return h
}

func (h *History) Push(s string) {
	if h == nil || s == "" {
		return
	}
	h.Reset()
	h.entries = append(h.entries, s)
	h.cap()
	_ = h.Save()
}

func (h *History) Prev() (string, bool) {
	if h == nil || len(h.entries) == 0 {
		return "", false
	}
	if h.cursor == -1 {
		h.cursor = len(h.entries) - 1
	} else if h.cursor > 0 {
		h.cursor--
	}
	return h.entries[h.cursor], true
}

func (h *History) Next() (string, bool) {
	if h == nil || h.cursor == -1 {
		return "", false
	}
	if h.cursor < len(h.entries)-1 {
		h.cursor++
		return h.entries[h.cursor], true
	}
	h.cursor = -1
	return "", true
}

func (h *History) Reset() {
	if h != nil {
		h.cursor = -1
	}
}

func (h *History) Save() error {
	if h == nil || h.path == "" {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(h.path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(h.entries, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(h.path, append(data, '\n'), 0o600)
}

func (h *History) Entries() []string {
	if h == nil {
		return nil
	}
	out := make([]string, len(h.entries))
	copy(out, h.entries)
	return out
}

func (h *History) load() {
	if h.path == "" {
		return
	}
	data, err := os.ReadFile(h.path)
	if err != nil {
		return
	}
	var entries []string
	if json.Unmarshal(data, &entries) == nil {
		h.entries = entries
		h.cap()
		return
	}
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	for scanner.Scan() {
		if s := scanner.Text(); s != "" {
			h.entries = append(h.entries, s)
		}
	}
	h.cap()
}

func (h *History) cap() {
	if h.max <= 0 {
		h.max = defaultHistoryMax
	}
	if over := len(h.entries) - h.max; over > 0 {
		h.entries = h.entries[over:]
	}
}

func expandPath(path string) string {
	if path == "" || path == "~" {
		if path == "~" {
			if home, err := os.UserHomeDir(); err == nil {
				return home
			}
		}
		return path
	}
	if strings.HasPrefix(path, "~/") {
		if home, err := os.UserHomeDir(); err == nil {
			return filepath.Join(home, path[2:])
		}
	}
	return path
}
