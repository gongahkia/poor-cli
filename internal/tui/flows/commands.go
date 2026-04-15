package flows

import (
	"context"
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/config"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets/commands"
)

const defaultCommandTimeout = 15 * time.Second

type StateDispatcher interface {
	Dispatch(action state.Action)
}

type Deps struct {
	RPC      RPCClient
	State    StateDispatcher
	Store    *state.Store
	Config   *config.Config
	Keymap   *config.Keymap
	Theme    *theme.Theme
	Registry *commands.Registry
	Context  func() context.Context
	Timeout  time.Duration
	Now      func() time.Time

	Toast              func(ToastKind, string) tea.Cmd
	OpenHelpModal      func(HelpPayload) tea.Cmd
	OpenCostModal      func(CostPayload) tea.Cmd
	OpenProviderPicker func(ProviderPayload) tea.Cmd
	OpenSessionPicker  func(SessionPayload) tea.Cmd
	OpenDiffReview     func(DiffPayload) tea.Cmd
	OpenWatchPanel     func(WatchPayload) tea.Cmd
	Quit               tea.Cmd
}

type CommandsFlow struct {
	rpc      RPCClient
	state    StateDispatcher
	registry *commands.Registry
	context  func() context.Context
	timeout  time.Duration
	now      func() time.Time

	toast              func(ToastKind, string) tea.Cmd
	openHelpModal      func(HelpPayload) tea.Cmd
	openCostModal      func(CostPayload) tea.Cmd
	openProviderPicker func(ProviderPayload) tea.Cmd
	openSessionPicker  func(SessionPayload) tea.Cmd
	openDiffReview     func(DiffPayload) tea.Cmd
	openWatchPanel     func(WatchPayload) tea.Cmd
	quit               tea.Cmd
}

type CommandDispatcher struct {
	flow *CommandsFlow
}

type CommandExecutor func(args string) tea.Cmd

type commandExecutorFactory func(*CommandsFlow) CommandExecutor

var executors = map[string]commandExecutorFactory{
	"/clear":    func(c *CommandsFlow) CommandExecutor { return c.cmdClear },
	"/compact":  func(c *CommandsFlow) CommandExecutor { return c.cmdCompact },
	"/quit":     func(c *CommandsFlow) CommandExecutor { return c.cmdQuit },
	"/help":     func(c *CommandsFlow) CommandExecutor { return c.cmdHelp },
	"/cost":     func(c *CommandsFlow) CommandExecutor { return c.cmdCost },
	"/provider": func(c *CommandsFlow) CommandExecutor { return c.cmdProvider },
	"/model":    func(c *CommandsFlow) CommandExecutor { return c.cmdModel },
	"/session":  func(c *CommandsFlow) CommandExecutor { return c.cmdSession },
	"/sessions": func(c *CommandsFlow) CommandExecutor { return c.cmdSession },
	"/diff":     func(c *CommandsFlow) CommandExecutor { return c.cmdDiff },
	"/watch":    func(c *CommandsFlow) CommandExecutor { return c.cmdWatch },
}

type ToastKind string

const (
	ToastInfo    ToastKind = "info"
	ToastSuccess ToastKind = "success"
	ToastWarning ToastKind = "warning"
	ToastError   ToastKind = "error"
)

type ToastMsg struct {
	Kind ToastKind
	Text string
}

type ModalKind string

const (
	ModalHelp           ModalKind = "help"
	ModalCost           ModalKind = "cost"
	ModalProviderPicker ModalKind = "provider_picker"
	ModalSessionPicker  ModalKind = "session_picker"
	ModalDiffReview     ModalKind = "diff_review"
	ModalWatchPanel     ModalKind = "watch_panel"
)

type OpenModalMsg struct {
	Kind    ModalKind
	Payload any
}

type HelpPayload struct {
	Commands []commands.Command
}

type CostPayload struct {
	Snapshot protocol.CostSnapshot
	Savings  protocol.SavingsSnapshot
	Loading  bool
	Error    string
}

type ProviderPayload struct {
	Providers protocol.ListProvidersResult
}

type SessionPayload struct {
	Sessions        []protocol.SessionSummary
	ActiveSessionID string
}

type DiffPayload struct {
	Edits []protocol.PendingEdit
}

type WatchPayload struct {
	Status map[string]any
}

func NewCommandsFlow(d Deps) *CommandsFlow {
	registry := d.Registry
	if registry == nil {
		registry = commands.NewRegistry()
	}
	timeout := d.Timeout
	if timeout <= 0 {
		timeout = defaultCommandTimeout
	}
	now := d.Now
	if now == nil {
		now = time.Now
	}
	f := &CommandsFlow{
		rpc:      d.RPC,
		state:    d.State,
		registry: registry,
		context:  d.Context,
		timeout:  timeout,
		now:      now,

		toast:              d.Toast,
		openHelpModal:      d.OpenHelpModal,
		openCostModal:      d.OpenCostModal,
		openProviderPicker: d.OpenProviderPicker,
		openSessionPicker:  d.OpenSessionPicker,
		openDiffReview:     d.OpenDiffReview,
		openWatchPanel:     d.OpenWatchPanel,
		quit:               d.Quit,
	}
	if f.toast == nil {
		f.toast = defaultToast
	}
	if f.openHelpModal == nil {
		f.openHelpModal = func(p HelpPayload) tea.Cmd { return emitCommand(OpenModalMsg{Kind: ModalHelp, Payload: p}) }
	}
	if f.openCostModal == nil {
		f.openCostModal = func(p CostPayload) tea.Cmd { return emitCommand(OpenModalMsg{Kind: ModalCost, Payload: p}) }
	}
	if f.openProviderPicker == nil {
		f.openProviderPicker = func(p ProviderPayload) tea.Cmd {
			return emitCommand(OpenModalMsg{Kind: ModalProviderPicker, Payload: p})
		}
	}
	if f.openSessionPicker == nil {
		f.openSessionPicker = func(p SessionPayload) tea.Cmd {
			return emitCommand(OpenModalMsg{Kind: ModalSessionPicker, Payload: p})
		}
	}
	if f.openDiffReview == nil {
		f.openDiffReview = func(p DiffPayload) tea.Cmd {
			return emitCommand(OpenModalMsg{Kind: ModalDiffReview, Payload: p})
		}
	}
	if f.quit == nil {
		f.quit = tea.Quit
	}
	return f
}

func NewCommandDispatcher(d Deps) *CommandDispatcher {
	return &CommandDispatcher{flow: NewCommandsFlow(d)}
}

func (d *CommandDispatcher) Dispatch(msg widgets.SelectCommandMsg) tea.Cmd {
	if d == nil || d.flow == nil {
		return defaultToast(ToastError, "command dispatcher unavailable")
	}
	return d.flow.DispatchSelect(msg)
}

func (c *CommandsFlow) DispatchSelect(msg widgets.SelectCommandMsg) tea.Cmd {
	return c.Dispatch(msg.CommandID, msg.Args)
}

func (c *CommandsFlow) Dispatch(commandID, args string) tea.Cmd {
	id := normalizeCommandID(commandID)
	if exec, ok := executors[id]; ok {
		return exec(c)(strings.TrimSpace(args))
	}
	if c.isCustom(id) {
		return c.cmdCustom(id, args)
	}
	return c.toast(ToastError, "unknown command: "+id)
}

func (c *CommandsFlow) SyncCustomCommands() tea.Cmd {
	return func() tea.Msg {
		var result customCommandList
		if err := c.call(protocol.MethodListCustomCommands, nil, &result); err != nil {
			return runCmd(c.toast(ToastError, fmt.Sprintf("failed to load custom commands: %v", err)))
		}
		c.registry.SetCustoms(result.Commands())
		return nil
	}
}

func (c *CommandsFlow) cmdClear(args string) tea.Cmd {
	return func() tea.Msg {
		c.dispatch(state.ActionReplaceMessages{Messages: []state.Message{}})
		return runCmd(c.toast(ToastSuccess, "conversation cleared"))
	}
}

func (c *CommandsFlow) cmdCompact(args string) tea.Cmd {
	return func() tea.Msg {
		var result map[string]any
		if err := c.call(protocol.MethodClearHistory, nil, &result); err != nil {
			return runCmd(c.toast(ToastError, fmt.Sprintf("compact failed: %v", err)))
		}
		c.dispatch(state.ActionReplaceMessages{Messages: []state.Message{}})
		return runCmd(c.toast(ToastSuccess, "conversation compacted"))
	}
}

func (c *CommandsFlow) cmdQuit(args string) tea.Cmd {
	return c.quit
}

func (c *CommandsFlow) cmdHelp(args string) tea.Cmd {
	return c.openHelpModal(HelpPayload{Commands: c.registry.All()})
}

func (c *CommandsFlow) cmdCost(args string) tea.Cmd {
	return func() tea.Msg {
		payload, err := c.fetchCostPayload()
		if err != nil {
			return runCmd(c.toast(ToastError, fmt.Sprintf("cost failed: %v", err)))
		}
		return runCmd(c.openCostModal(payload))
	}
}

func (c *CommandsFlow) cmdProvider(args string) tea.Cmd {
	if args != "" {
		return c.switchProvider(args, "")
	}
	return func() tea.Msg {
		var result protocol.ListProvidersResult
		if err := c.call(protocol.MethodListProviders, nil, &result); err != nil {
			return runCmd(c.toast(ToastError, fmt.Sprintf("providers failed: %v", err)))
		}
		return runCmd(c.openProviderPicker(ProviderPayload{Providers: result}))
	}
}

func (c *CommandsFlow) cmdModel(args string) tea.Cmd {
	if strings.TrimSpace(args) == "" {
		return c.cmdProvider("")
	}
	return c.switchProvider("", args)
}

func (c *CommandsFlow) cmdSession(args string) tea.Cmd {
	if args != "" {
		return func() tea.Msg {
			var result protocol.SwitchSessionResult
			params := protocol.SwitchSessionParams{SessionID: args}
			if err := c.call(protocol.MethodSwitchSession, params, &result); err != nil {
				return runCmd(c.toast(ToastError, fmt.Sprintf("switch session failed: %v", err)))
			}
			if result.Error != "" {
				return runCmd(c.toast(ToastError, "switch session failed: "+result.Error))
			}
			return runCmd(c.toast(ToastSuccess, "session switched"))
		}
	}
	return func() tea.Msg {
		var result protocol.ListSessionsResult
		if err := c.call(protocol.MethodListSessions, nil, &result); err != nil {
			return runCmd(c.toast(ToastError, fmt.Sprintf("sessions failed: %v", err)))
		}
		return runCmd(c.openSessionPicker(SessionPayload{Sessions: result.Sessions, ActiveSessionID: result.ActiveSessionID}))
	}
}

func (c *CommandsFlow) cmdDiff(args string) tea.Cmd {
	return func() tea.Msg {
		var result protocol.DiffListResult
		if err := c.call(protocol.MethodListPendingEdits, protocol.DiffListParams{}, &result); err != nil {
			return runCmd(c.toast(ToastError, fmt.Sprintf("diff failed: %v", err)))
		}
		edits := make([]protocol.PendingEdit, len(result.Edits))
		copy(edits, result.Edits)
		return runCmd(c.openDiffReview(DiffPayload{Edits: edits}))
	}
}

func (c *CommandsFlow) cmdWatch(args string) tea.Cmd {
	return func() tea.Msg {
		var result map[string]any
		if err := c.call(protocol.MethodContextStatus, nil, &result); err != nil {
			return runCmd(c.toast(ToastError, fmt.Sprintf("watch failed: %v", err)))
		}
		if c.openWatchPanel != nil {
			if msg := runCmd(c.openWatchPanel(WatchPayload{Status: result})); msg != nil {
				return msg
			}
		}
		return runCmd(c.toast(ToastInfo, "watch panel toggled"))
	}
}

func (c *CommandsFlow) cmdCustom(commandID, args string) tea.Cmd {
	return func() tea.Msg {
		name := strings.TrimPrefix(commandID, "/")
		params := map[string]any{"name": name, "argsText": strings.TrimSpace(args)}
		var result map[string]any
		if err := c.call(protocol.MethodRunCustomCommand, params, &result); err != nil {
			return runCmd(c.toast(ToastError, fmt.Sprintf("custom command failed: %v", err)))
		}
		return runCmd(c.toast(ToastSuccess, "custom command queued"))
	}
}

func (c *CommandsFlow) switchProvider(provider, model string) tea.Cmd {
	return func() tea.Msg {
		params := protocol.SwitchProviderParams{Provider: strings.TrimSpace(provider), Model: strings.TrimSpace(model)}
		var result protocol.SwitchProviderResult
		if err := c.call(protocol.MethodSwitchProvider, params, &result); err != nil {
			return runCmd(c.toast(ToastError, fmt.Sprintf("switch provider failed: %v", err)))
		}
		if result.Error != "" {
			return runCmd(c.toast(ToastError, "switch provider failed: "+result.Error))
		}
		if !result.Success {
			return runCmd(c.toast(ToastError, "switch provider failed"))
		}
		if result.Provider.Name != "" || result.Provider.Model != "" {
			c.dispatch(state.ActionSetProvider{Info: result.Provider})
		}
		return runCmd(c.toast(ToastSuccess, "provider switched"))
	}
}

func (c *CommandsFlow) call(method string, params any, result any) error {
	if c.rpc == nil {
		return fmt.Errorf("rpc unavailable")
	}
	ctx := context.Background()
	if c.context != nil {
		ctx = c.context()
	}
	if ctx == nil {
		ctx = context.Background()
	}
	var cancel context.CancelFunc
	if _, ok := ctx.Deadline(); !ok && c.timeout > 0 {
		ctx, cancel = context.WithTimeout(ctx, c.timeout)
		defer cancel()
	}
	return c.rpc.Call(ctx, method, params, result)
}

func (c *CommandsFlow) fetchCostPayload() (CostPayload, error) {
	var payload CostPayload
	if err := c.call(protocol.MethodCostSummary, nil, &payload.Snapshot); err != nil {
		if fallback := c.call(protocol.MethodGetSessionCost, nil, &payload.Snapshot); fallback != nil {
			return payload, err
		}
	}
	if err := c.call(protocol.MethodGetEconomySavings, nil, &payload.Savings); err != nil {
		return payload, err
	}
	return payload, nil
}

func (c *CommandsFlow) dispatch(action state.Action) {
	if c.state != nil {
		c.state.Dispatch(action)
	}
}

func (c *CommandsFlow) isCustom(commandID string) bool {
	for _, cmd := range c.registry.All() {
		if cmd.Origin == commands.OriginCustom && normalizeCommandID(cmd.ID) == commandID {
			return true
		}
	}
	return false
}

func defaultToast(kind ToastKind, text string) tea.Cmd {
	return emitCommand(ToastMsg{Kind: kind, Text: text})
}

func emitCommand(msg tea.Msg) tea.Cmd {
	return func() tea.Msg {
		return msg
	}
}

func runCmd(cmd tea.Cmd) tea.Msg {
	if cmd == nil {
		return nil
	}
	return cmd()
}

func normalizeCommandID(id string) string {
	id = strings.TrimSpace(id)
	if id == "" {
		return "/"
	}
	id = strings.Fields(id)[0]
	id = strings.ToLower(id)
	if !strings.HasPrefix(id, "/") {
		id = "/" + id
	}
	return id
}

type customCommandList struct {
	CommandsRaw []customCommand `json:"commands"`
}

func (l customCommandList) Commands() []commands.Command {
	out := make([]commands.Command, 0, len(l.CommandsRaw))
	for _, raw := range l.CommandsRaw {
		id := strings.TrimSpace(firstNonEmpty(raw.ID, raw.Command, raw.Name))
		if id == "" {
			continue
		}
		if !strings.HasPrefix(id, "/") {
			id = "/" + id
		}
		out = append(out, commands.Command{
			ID:          id,
			Label:       id,
			Description: raw.Description,
			Usage:       firstNonEmpty(raw.Usage, id),
			Origin:      commands.OriginCustom,
			RequiresArg: raw.RequiresArg,
		})
	}
	return out
}

type customCommand struct {
	ID          string `json:"id,omitempty"`
	Command     string `json:"command,omitempty"`
	Name        string `json:"name,omitempty"`
	Description string `json:"description,omitempty"`
	Usage       string `json:"usage,omitempty"`
	RequiresArg bool   `json:"requiresArg,omitempty"`
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}
