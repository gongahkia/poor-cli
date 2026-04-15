package server

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestResolveBinaryMissing(t *testing.T) {
	t.Setenv("POOR_CLI_SERVER_PATH", "")
	t.Setenv("PATH", t.TempDir())
	_, err := ResolveBinary("")
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "poor-cli-server not found") || !strings.Contains(err.Error(), "POOR_CLI_SERVER_PATH") {
		t.Fatalf("unhelpful error: %v", err)
	}
}

func TestResolveBinaryPrefersEnv(t *testing.T) {
	path := fakeServerScript(t, "echo ready >&2\n")
	t.Setenv("POOR_CLI_SERVER_PATH", path)
	got, err := ResolveBinary("")
	if err != nil {
		t.Fatal(err)
	}
	if got != path {
		t.Fatalf("got %q want %q", got, path)
	}
}

func TestManagerStderrRingBuffer(t *testing.T) {
	path := fakeServerScript(t, "for i in $(seq 1 1000); do echo log-$i >&2; done\nsleep 2\n")
	m := NewManager(Config{BinaryPath: path, ReadyTimeout: time.Second, StderrRingLines: 100})
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := m.Start(ctx); err != nil {
		t.Fatal(err)
	}
	waitFor(t, 3*time.Second, func() bool {
		tail := m.TailStderr(100)
		return len(tail) == 100 && tail[99] == "log-1000"
	})
	tail := m.TailStderr(100)
	if len(tail) != 100 {
		t.Fatalf("tail len=%d", len(tail))
	}
	if tail[0] != "log-901" || tail[99] != "log-1000" {
		t.Fatalf("bad tail: first=%q last=%q", tail[0], tail[99])
	}
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer shutdownCancel()
	if err := m.Shutdown(shutdownCtx); err != nil {
		t.Fatal(err)
	}
}

func TestManagerShutdownEscalates(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell fake uses Unix signals")
	}
	path := fakeServerScript(t, "trap '' TERM\n echo ready >&2\n while true; do sleep 1; done\n")
	m := NewManager(Config{BinaryPath: path, ReadyTimeout: time.Second, ShutdownTimeout: 100 * time.Millisecond})
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := m.Start(ctx); err != nil {
		t.Fatal(err)
	}
	if err := m.Shutdown(ctx); err != nil {
		t.Fatal(err)
	}
	err := m.Wait()
	var exitErr *exec.ExitError
	if !errors.As(err, &exitErr) {
		t.Fatalf("Wait err=%v", err)
	}
	status, ok := exitErr.Sys().(syscall.WaitStatus)
	if !ok || !status.Signaled() {
		t.Fatalf("want signaled exit, got %v", err)
	}
	if sig := status.Signal(); sig != syscall.SIGKILL && sig != syscall.SIGTERM {
		t.Fatalf("want SIGKILL/SIGTERM, got %v", err)
	}
}

func TestManagerStartupReady(t *testing.T) {
	path := fakeServerScript(t, "echo session-id=test >&2\ncat >/dev/null\n")
	m := NewManager(Config{BinaryPath: path, ReadyTimeout: time.Second})
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	start := time.Now()
	if err := m.Start(ctx); err != nil {
		t.Fatal(err)
	}
	if time.Since(start) > 2*time.Second {
		t.Fatalf("Start took too long: %s", time.Since(start))
	}
	if m.PID() == 0 {
		t.Fatal("missing pid")
	}
	if m.Stdin() == nil || m.Stdout() == nil {
		t.Fatal("missing stdio pipes")
	}
	if err := m.Shutdown(ctx); err != nil {
		t.Fatal(err)
	}
}

func TestManagerStartupExitIncludesTail(t *testing.T) {
	m := NewManager(Config{})
	m.waitErr = errors.New("exit status 7")
	m.ring.add("boom")
	err := m.waitErrorWithTail()
	if !strings.Contains(err.Error(), "stderr tail") || !strings.Contains(err.Error(), "boom") {
		t.Fatalf("bad error: %v", err)
	}
}

func fakeServerScript(t *testing.T, body string) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("shell fake not supported on windows")
	}
	path := filepath.Join(t.TempDir(), "poor-cli-server")
	content := fmt.Sprintf("#!/bin/sh\n%s", body)
	if err := os.WriteFile(path, []byte(content), 0700); err != nil {
		t.Fatal(err)
	}
	return path
}

func waitFor(t *testing.T, timeout time.Duration, ok func() bool) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if ok() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("condition timed out")
}
