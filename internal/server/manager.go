package server

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"sort"
	"sync"
	"time"
)

type Config struct {
	BinaryPath      string
	Args            []string
	Env             map[string]string
	Cwd             string
	Logger          *slog.Logger
	ReadyTimeout    time.Duration
	ShutdownTimeout time.Duration
	StderrRingLines int
}

type Manager struct {
	cfg Config

	mu       sync.Mutex
	cmd      *exec.Cmd
	stdin    io.WriteCloser
	stdout   io.ReadCloser
	waitDone chan struct{}
	waitErr  error
	ring     *stderrRing
	health   HealthStatus
}

func NewManager(cfg Config) *Manager {
	size := cfg.StderrRingLines
	if size <= 0 {
		size = 500
	}
	return &Manager{cfg: cfg, ring: newStderrRing(size), health: HealthUnknown}
}

func (m *Manager) Start(ctx context.Context) error {
	m.mu.Lock()
	if m.cmd != nil && m.waitDone != nil {
		select {
		case <-m.waitDone:
		default:
			m.mu.Unlock()
			return fmt.Errorf("server: process already started")
		}
	}
	m.mu.Unlock()

	bin, err := ResolveBinary(m.cfg.BinaryPath)
	if err != nil {
		return err
	}

	args := append([]string{"--stdio"}, m.cfg.Args...)
	cmd := exec.Command(bin, args...)
	cmd.Dir = m.cfg.Cwd
	cmd.Env = mergedEnv(m.cfg.Env)
	prepareCmd(cmd)

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("server: stdin pipe: %w", err)
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("server: stdout pipe: %w", err)
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return fmt.Errorf("server: stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("server: start %q: %w", bin, err)
	}

	waitDone := make(chan struct{})
	firstStderr := make(chan struct{})

	m.mu.Lock()
	m.cmd = cmd
	m.stdin = stdin
	m.stdout = stdout
	m.waitDone = waitDone
	m.waitErr = nil
	m.health = HealthHealthy
	m.mu.Unlock()

	go m.readStderr(stderr, firstStderr)
	go func() {
		err := cmd.Wait()
		m.mu.Lock()
		m.waitErr = err
		m.health = HealthUnhealthy
		m.mu.Unlock()
		close(waitDone)
	}()

	timer := time.NewTimer(m.readyTimeout())
	defer timer.Stop()

	select {
	case <-firstStderr:
		return nil
	case <-timer.C:
		select {
		case <-waitDone:
			return m.waitErrorWithTail()
		default:
			return nil
		}
	case <-waitDone:
		return m.waitErrorWithTail()
	case <-ctx.Done():
		_ = killProcess(cmd)
		<-waitDone
		return ctx.Err()
	}
}

func (m *Manager) Stdin() io.Writer {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.stdin
}

func (m *Manager) Stdout() io.Reader {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.stdout
}

func (m *Manager) Wait() error {
	m.mu.Lock()
	waitDone := m.waitDone
	m.mu.Unlock()
	if waitDone == nil {
		return nil
	}
	<-waitDone
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.waitErr
}

func (m *Manager) Shutdown(ctx context.Context) error {
	m.mu.Lock()
	cmd := m.cmd
	stdin := m.stdin
	waitDone := m.waitDone
	m.mu.Unlock()
	if cmd == nil || waitDone == nil {
		return nil
	}

	select {
	case <-waitDone:
		return nil
	default:
	}

	if stdin != nil {
		_ = stdin.Close()
	}
	if err := terminateProcess(cmd); err != nil {
		select {
		case <-waitDone:
			return nil
		default:
			return err
		}
	}

	timer := time.NewTimer(m.shutdownTimeout())
	defer timer.Stop()

	select {
	case <-waitDone:
		return nil
	case <-timer.C:
	case <-ctx.Done():
	}

	if err := killProcess(cmd); err != nil {
		select {
		case <-waitDone:
			return nil
		default:
			return err
		}
	}

	select {
	case <-waitDone:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (m *Manager) TailStderr(n int) []string {
	return m.ring.tail(n)
}

func (m *Manager) PID() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.cmd == nil || m.cmd.Process == nil {
		return 0
	}
	return m.cmd.Process.Pid
}

func (m *Manager) readStderr(r io.Reader, firstLine chan<- struct{}) {
	var file *os.File
	if path := m.logFilePath(); path != "" {
		f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
		if err == nil {
			file = f
			defer file.Close()
		} else if m.cfg.Logger != nil {
			m.cfg.Logger.Warn("server log file open failed", "path", path, "error", err)
		}
	}

	var once sync.Once
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		m.ring.add(line)
		if file != nil {
			_, _ = file.WriteString(line + "\n")
		}
		once.Do(func() { close(firstLine) })
	}
	if err := scanner.Err(); err != nil && m.cfg.Logger != nil {
		m.cfg.Logger.Warn("server stderr read failed", "error", err)
	}
}

func (m *Manager) readyTimeout() time.Duration {
	if m.cfg.ReadyTimeout > 0 {
		return m.cfg.ReadyTimeout
	}
	return 500 * time.Millisecond
}

func (m *Manager) shutdownTimeout() time.Duration {
	if m.cfg.ShutdownTimeout > 0 {
		return m.cfg.ShutdownTimeout
	}
	return 3 * time.Second
}

func (m *Manager) waitErrorWithTail() error {
	m.mu.Lock()
	err := m.waitErr
	m.mu.Unlock()
	if err == nil {
		return fmt.Errorf("server: exited during startup")
	}
	tail := m.TailStderr(5)
	if len(tail) == 0 {
		return fmt.Errorf("server: exited during startup: %w", err)
	}
	return fmt.Errorf("server: exited during startup: %w; stderr tail: %q", err, tail)
}

func (m *Manager) logFilePath() string {
	if m.cfg.Env != nil {
		if path := m.cfg.Env["POOR_CLI_SERVER_LOG_FILE"]; path != "" {
			return path
		}
	}
	return os.Getenv("POOR_CLI_SERVER_LOG_FILE")
}

func mergedEnv(extra map[string]string) []string {
	env := map[string]string{}
	for _, item := range os.Environ() {
		for i := 0; i < len(item); i++ {
			if item[i] == '=' {
				env[item[:i]] = item[i+1:]
				break
			}
		}
	}
	for k, v := range extra {
		env[k] = v
	}
	keys := make([]string, 0, len(env))
	for k := range env {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := make([]string, 0, len(keys))
	for _, k := range keys {
		out = append(out, k+"="+env[k])
	}
	return out
}

type stderrRing struct {
	mu     sync.Mutex
	lines  []string
	next   int
	filled bool
}

func newStderrRing(size int) *stderrRing {
	return &stderrRing{lines: make([]string, size)}
}

func (r *stderrRing) add(line string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if len(r.lines) == 0 {
		return
	}
	r.lines[r.next] = line
	r.next = (r.next + 1) % len(r.lines)
	if r.next == 0 {
		r.filled = true
	}
}

func (r *stderrRing) tail(n int) []string {
	r.mu.Lock()
	defer r.mu.Unlock()
	if n <= 0 || len(r.lines) == 0 {
		return nil
	}
	size := r.next
	if r.filled {
		size = len(r.lines)
	}
	if n > size {
		n = size
	}
	out := make([]string, 0, n)
	start := (r.next - n + len(r.lines)) % len(r.lines)
	for i := 0; i < n; i++ {
		out = append(out, r.lines[(start+i)%len(r.lines)])
	}
	return out
}
