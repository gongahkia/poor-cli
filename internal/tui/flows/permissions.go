package flows

import (
	"context"
	"errors"
	"fmt"
	"math"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/protocol"
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
		body = m.Flow.render(width-2, height-2, now)
	}
	return lipgloss.NewStyle().
		Width(width).
		Height(height).
		Border(lipgloss.NormalBorder()).
		Render(body)
}

func (f *PermissionFlow) render(width, height int, now time.Time) string {
	lines := []string{
		fit("Permission requested", width),
		fit("Tool: "+nonEmpty(f.req.ToolName, "unknown"), width),
		fit("Rationale: "+permissionRationale(f.req), width),
		fit("", width),
	}
	command := permissionCommand(f.req)
	if command != "" {
		lines = append(lines, fit("Command:", width))
		for _, line := range strings.Split(command, "\n") {
			lines = append(lines, fit("  "+line, width))
		}
	} else if len(f.req.Paths) > 0 {
		lines = append(lines, fit("Paths: "+strings.Join(f.req.Paths, ", "), width))
	}
	lines = append(lines, fit("", width))
	lines = append(lines, fit(countdownBar(f.Remaining(now), f.timeout, width), width))
	lines = append(lines, fit("[A] allow once  [S] allow session", width))
	lines = append(lines, fit("[P] allow permanently  [D] deny  [Esc] deny", width))
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

func countdownBar(remaining, timeout time.Duration, width int) string {
	if timeout <= 0 {
		timeout = DefaultPermissionTimeout
	}
	seconds := int(math.Ceil(remaining.Seconds()))
	if seconds < 0 {
		seconds = 0
	}
	label := fmt.Sprintf("timeout: %ds ", seconds)
	barWidth := max(1, width-lipgloss.Width(label)-2)
	pct := float64(remaining) / float64(timeout)
	if pct < 0 {
		pct = 0
	}
	if pct > 1 {
		pct = 1
	}
	filled := int(math.Round(float64(barWidth) * pct))
	if filled > barWidth {
		filled = barWidth
	}
	return label + "[" + strings.Repeat("#", filled) + strings.Repeat("-", barWidth-filled) + "]"
}
