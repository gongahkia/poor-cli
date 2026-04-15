package flows

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
)

const DefaultPermissionTimeout = 30 * time.Second

var ErrPermissionTimedOut = errors.New("permission: request timed out")

type Notifier interface {
	Notify(ctx context.Context, method string, params any) error
}

type PermissionFlow struct {
	rpc     Notifier
	req     protocol.PermissionReq
	started time.Time
	timeout time.Duration
	open    bool
}

type PermissionModal struct {
	Flow   *PermissionFlow
	Width  int
	Height int
	Now    time.Time
}

func NewPermissionFlow(rpc Notifier, timeout time.Duration) *PermissionFlow {
	if timeout <= 0 {
		timeout = DefaultPermissionTimeout
	}
	return &PermissionFlow{rpc: rpc, timeout: timeout}
}

func (f *PermissionFlow) Open(req protocol.PermissionReq, now time.Time) {
	if now.IsZero() {
		now = time.Now()
	}
	f.req = req
	f.started = now
	f.open = true
}

func (f *PermissionFlow) HandleKey(ctx context.Context, key string) error {
	switch key {
	case "A", "a":
		return f.Decide(ctx, "allow", "once")
	case "S", "s":
		return f.Decide(ctx, "allow", "session")
	case "P", "p":
		return f.Decide(ctx, "allow", "permanent")
	case "D", "d", "esc":
		return f.Decide(ctx, "deny", "once")
	default:
		return nil
	}
}

func (f *PermissionFlow) Decide(ctx context.Context, decision, rememberScope string) error {
	if !f.open {
		return nil
	}
	remaining := f.Remaining(time.Now())
	if remaining <= 0 {
		f.open = false
		return ErrPermissionTimedOut
	}
	if f.rpc == nil {
		return errors.New("permission: nil rpc")
	}
	var cancel context.CancelFunc
	ctx, cancel = context.WithTimeout(ctx, remaining)
	defer cancel()
	allowed := decision == "allow"
	res := protocol.PermissionRes{
		RequestID:     f.req.RequestID,
		RequestKey:    f.req.RequestKey,
		PromptID:      f.req.PromptID,
		Decision:      decision,
		Allowed:       &allowed,
		RememberScope: rememberScope,
	}
	if err := f.rpc.Notify(ctx, protocol.MethodPermissionRes, res); err != nil {
		return err
	}
	f.open = false
	return nil
}

func (f *PermissionFlow) Remaining(now time.Time) time.Duration {
	if now.IsZero() {
		now = time.Now()
	}
	if f.started.IsZero() {
		return f.timeout
	}
	remaining := f.timeout - now.Sub(f.started)
	if remaining < 0 {
		return 0
	}
	return remaining
}

func (f *PermissionFlow) Opened() bool {
	return f.open
}

func (f *PermissionFlow) Request() protocol.PermissionReq {
	return f.req
}

func (f *PermissionFlow) View(width, height int, now time.Time) string {
	return PermissionModal{Flow: f, Width: width, Height: height, Now: now}.View()
}

func (m PermissionModal) View() string {
	width := max(20, m.Width)
	height := max(8, m.Height)
	body := "no permission request"
	if m.Flow != nil && m.Flow.open {
		now := m.Now
		if now.IsZero() {
			now = time.Now()
		}
		body = m.Flow.render(width, height, now)
	}
	return body
}

func (f *PermissionFlow) render(width, height int, now time.Time) string {
	lines := []string{
		fit(widgets.FlushHeader(nil, fmt.Sprintf("permission · %ds", int(f.Remaining(now).Seconds()))), width),
		fit("tool · "+nonEmpty(f.req.ToolName, "unknown"), width),
		fit("why · "+permissionRationale(f.req), width),
		fit("", width),
	}
	command := permissionCommand(f.req)
	if command != "" {
		lines = append(lines, fit("cmd", width))
		for _, line := range strings.Split(command, "\n") {
			lines = append(lines, fit("  "+line, width))
		}
	} else if len(f.req.Paths) > 0 {
		lines = append(lines, fit("paths · "+strings.Join(f.req.Paths, ", "), width))
	}
	lines = append(lines, fit("", width))
	lines = append(lines, fit("[a] once  [s] session", width))
	lines = append(lines, fit("[p] always  [d] deny  [esc] deny", width))
	for len(lines) < height {
		lines = append(lines, fit("", width))
	}
	if len(lines) > height {
		lines = lines[:height]
	}
	return strings.Join(lines, "\n")
}

func permissionRationale(req protocol.PermissionReq) string {
	for _, value := range []string{req.Rationale, req.Description, req.Message, req.Operation} {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return "server requested approval"
}

func permissionCommand(req protocol.PermissionReq) string {
	for _, key := range []string{"command", "cmd", "script"} {
		if v, ok := req.ToolArgs[key].(string); ok && strings.TrimSpace(v) != "" {
			return v
		}
		if v, ok := req.Details[key].(string); ok && strings.TrimSpace(v) != "" {
			return v
		}
	}
	if len(req.ToolArgs) == 0 {
		return ""
	}
	return fmt.Sprint(req.ToolArgs)
}
