package tui

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

type clipboardImageMsg struct {
	Path string
	Err  error
}

func pasteClipboardImageCmd() tea.Cmd {
	return func() tea.Msg {
		path, err := saveClipboardImage()
		return clipboardImageMsg{Path: path, Err: err}
	}
}

func saveClipboardImage() (string, error) {
	dir, err := clipboardImageDir()
	if err != nil {
		return "", err
	}
	out := filepath.Join(dir, fmt.Sprintf("clipboard-%d.png", time.Now().UnixNano()))
	if path, err := clipboardPathText(); err == nil && path != "" {
		return path, nil
	}
	if err := runPngpaste(out); err == nil {
		return out, nil
	}
	if err := runAppleScriptPNG(out); err == nil {
		return out, nil
	}
	return "", errors.New("clipboard has no supported image")
}

func clipboardImageDir() (string, error) {
	dir, err := os.UserCacheDir()
	if err != nil {
		dir = os.TempDir()
	}
	dir = filepath.Join(dir, "poor-cli", "clipboard")
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	return dir, nil
}

func clipboardPathText() (string, error) {
	out, err := exec.Command("pbpaste").Output()
	if err != nil {
		return "", err
	}
	path := strings.TrimSpace(string(out))
	if path == "" || strings.Contains(path, "\n") {
		return "", nil
	}
	ext := strings.ToLower(filepath.Ext(path))
	switch ext {
	case ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp":
	default:
		return "", nil
	}
	info, err := os.Stat(path)
	if err != nil || info.IsDir() {
		return "", nil
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return path, nil
	}
	return abs, nil
}

func runPngpaste(out string) error {
	if _, err := exec.LookPath("pngpaste"); err != nil {
		return err
	}
	return exec.Command("pngpaste", out).Run()
}

func runAppleScriptPNG(out string) error {
	script := fmt.Sprintf(`
set outPath to POSIX file "%s"
set fref to open for access outPath with write permission
try
	set eof fref to 0
	write (the clipboard as «class PNGf») to fref
	close access fref
on error errMsg
	try
		close access fref
	end try
	error errMsg
end try
`, strings.ReplaceAll(out, `"`, `\"`))
	return exec.Command("osascript", "-e", script).Run()
}
