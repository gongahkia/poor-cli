package tui

import (
	"context"
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
	"github.com/gongahkia/gocli-poor/internal/tui/flows"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets"
	"github.com/gongahkia/gocli-poor/internal/tui/widgets/commands"
)

const defaultIntroVersion = "v0.0.0"

type Model struct {
	State            *state.AppState
	Width            int
	Height           int
	Regions          Regions
	Focus            FocusRouter
	Modals           ModalStack
	Input            string
	ChatScrollAnchor int
	Toast            ToastMsg
	Intro            IntroModel
	Store            *state.Store
	Chat             *widgets.ChatView
	Users            *widgets.UsersPanel
	UsersOpen        bool
	connectCmd       tea.Cmd
	rpc              flows.RPCClient
	registry         *flows.Registry
	usersFlow        *flows.UsersFlow
	stateUpdates     <-chan state.AppState
	unsubscribeState func()
	uiRevision       uint64
	viewCache        *modelViewCache
}

type modelViewCache struct {
	key   modelViewKey
	value string
	valid bool
}

type modelViewKey struct {
	stateRevision   uint64
	uiRevision      uint64
	width           int
	height          int
	regions         Regions
	focus           FocusTarget
	input           string
	chatScroll      int
	toastText       string
	toastKind       ToastKind
	introActive     bool
	introVersion    string
	usersOpen       bool
	modalSignature  string
	typingFooterRow int
}

type Option func(*Model)

func WithConnectCmd(cmd tea.Cmd) Option {
	return func(m *Model) {
		m.connectCmd = cmd
	}
}

func WithIntroVersion(version string) Option {
	return func(m *Model) {
		m.Intro.Version = version
	}
}

func WithRPCClient(rpc flows.RPCClient) Option {
	return func(m *Model) {
		m.rpc = rpc
	}
}

func NewModel(appState *state.AppState, opts ...Option) Model {
	initial := state.AppState{Connection: state.ConnState{Phase: state.Disconnected}}
	if appState != nil {
		initial = *appState
	}
	m := Model{
		State:     &initial,
		Store:     state.NewStoreWithState(initial),
		Chat:      widgets.NewChatView(widgets.ChatDeps{}),
		Users:     widgets.NewUsersPanel(nil),
		Focus:     FocusRouter{Target: FocusIntro},
		Intro:     IntroModel{Active: true, Version: defaultIntroVersion},
		Width:     80,
		Height:    24,
		viewCache: &modelViewCache{},
	}
	for _, opt := range opts {
		opt(&m)
	}
	m.Chat.SetMultiplayer(initial.Multiplayer)
	m.Chat.SetMessages(initial.Messages)
	m.Users.SetState(initial.Multiplayer)
	m.stateUpdates, m.unsubscribeState = m.Store.Subscribe()
	m.registry = flows.NewRegistry()
	m.registry.Register(flows.NewChatFlow(flows.Deps{RPC: m.rpc, Store: m.Store, State: m.Store}))
	m.registry.Register(flows.NewPresenceFlow(flows.Deps{RPC: m.rpc, Store: m.Store, State: m.Store}))
	m.registry.Register(flows.NewHudFlow(flows.Deps{RPC: m.rpc, Store: m.Store, State: m.Store}))
	m.registry.Register(flows.NewVotingFlow(flows.Deps{RPC: m.rpc, Store: m.Store, State: m.Store}))
	m.usersFlow = flows.NewUsersFlow(flows.Deps{RPC: m.rpc, Store: m.Store, State: m.Store})
	m.registry.Register(m.usersFlow)
	m.relayout()
	return m
}

func NewProgram(appState *state.AppState, opts ...Option) *tea.Program {
	return tea.NewProgram(NewModel(appState, opts...), tea.WithAltScreen(), tea.WithMouseCellMotion())
}

func Run(appState *state.AppState, opts ...Option) error {
	_, err := NewProgram(appState, opts...).Run()
	return err
}

func (m Model) Init() tea.Cmd {
	return tea.Batch(m.connectCmd, tea.EnableBracketedPaste, introTimeoutCmd(), m.startFlowsCmd(), waitStateUpdate(m.stateUpdates))
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	trace := traceStart("update", fmt.Sprintf("%T", msg))
	defer traceDone("update", trace, m.Width, m.Height)
	flowCmds := m.registry.UpdateAll(msg)
	batch := func(cmds ...tea.Cmd) tea.Cmd {
		return tea.Batch(append(flowCmds, cmds...)...)
	}
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.resize(msg.Width, msg.Height)
		return m, batch()
	case ResizeMsg:
		m.resize(msg.Width, msg.Height)
		return m, batch()
	case stateUpdatedMsg:
		m.State = &msg.State
		if m.Chat != nil {
			m.Chat.SetMultiplayer(msg.State.Multiplayer)
			m.Chat.SetMessages(msg.State.Messages)
		}
		if m.Users != nil {
			m.Users.SetState(msg.State.Multiplayer)
		}
		if !msg.State.Multiplayer.Enabled && m.UsersOpen {
			m.UsersOpen = false
			if m.Focus.Target == FocusUsers {
				m.setFocus(FocusInput)
			}
			m.relayout()
		}
		m.relayout()
		return m, batch(waitStateUpdate(m.stateUpdates))
	case IntroDoneMsg:
		m.closeIntro()
		return m, batch()
	case InitializeOKMsg:
		m.closeIntro()
		return m, batch()
	case InitializeNeedsAPIKeyMsg:
		m.closeIntro()
		m.openModal(ModalAPIKeyPrompt, flows.NewAPIKeyPrompt(msg.Provider, msg.Message))
		return m, batch()
	case SwitchFocusMsg:
		m.setFocus(msg.Target)
		return m, batch()
	case OpenModalMsg:
		m.openModal(msg.Kind, msg.Payload)
		return m, batch(m.openModalCmd(msg.Kind, msg.Payload))
	case CloseModalMsg:
		m.closeModal()
		return m, batch()
	case widgets.SelectCommandMsg:
		m.closeModal()
		input := strings.TrimSpace(msg.CommandID + " " + msg.Args)
		return m, batch(m.dispatchCommandInput(input))
	case widgets.ClosePaletteMsg:
		m.closeModal()
		m.Input = msg.Residual
		m.relayout()
		return m, batch()
	case flows.ProvidersLoadedMsg:
		m.withTopProviderPicker(func(p *flows.ProviderPicker) { p.ApplyLoaded(msg) })
		m.markDirty()
		return m, batch()
	case flows.ProviderSelectedMsg:
		previous := m.currentProviderInfo()
		m.dispatchState(state.ActionSetProvider{Info: protocol.ProviderInfo{Name: msg.Choice.Provider, Model: msg.Choice.Model}})
		return m, batch(flows.SwitchProviderCmd(m.rpc, msg.Choice, previous))
	case flows.ProviderSwitchedMsg:
		if msg.Err != nil {
			m.dispatchState(state.ActionSetProvider{Info: msg.Previous})
			m.Toast = ToastMsg{Kind: ToastError, Text: msg.Err.Error(), TTL: 3 * time.Second}
			return m, batch()
		}
		info := msg.Result.Provider
		if info.Name == "" {
			info = protocol.ProviderInfo{Name: msg.Choice.Provider, Model: msg.Choice.Model}
		}
		m.dispatchState(state.ActionSetProvider{Info: info})
		m.closeModal()
		if !msg.Choice.Detail.Ready {
			m.openModal(ModalAPIKeyPrompt, flows.NewAPIKeyPrompt(msg.Choice.Provider, ""))
		}
		return m, batch()
	case flows.SessionsLoadedMsg:
		m.withTopSessionPicker(func(p *flows.SessionPicker) { p.ApplyLoaded(msg) })
		m.markDirty()
		return m, batch()
	case flows.SessionSelectedMsg:
		return m, batch(flows.SwitchSessionCmd(m.rpc, msg.Session))
	case flows.SessionSwitchedMsg:
		if msg.Err != nil {
			m.Toast = ToastMsg{Kind: ToastError, Text: msg.Err.Error(), TTL: 3 * time.Second}
			return m, batch()
		}
		session := msg.Result.Session
		if session.SessionID == "" && session.ID == "" {
			session = msg.Session
		}
		sessionID := flowSessionID(session)
		m.dispatchState(state.ActionSetSession{SessionID: sessionID, Turns: session.MessageCount})
		m.closeModal()
		return m, batch(flows.FetchCheckpointsCmd(m.rpc, sessionID))
	case flows.CheckpointsLoadedMsg:
		if msg.Err != nil {
			m.Toast = ToastMsg{Kind: ToastError, Text: msg.Err.Error(), TTL: 3 * time.Second}
			return m, batch()
		}
		m.dispatchState(state.ActionSetSession{SessionID: msg.SessionID, Checkpoints: convertCheckpoints(msg.Result.Checkpoints)})
		return m, batch()
	case flows.CostModalLoadedMsg:
		m.withTopCostPayload(func(p *flows.CostPayload) { *p = msg.Payload })
		if msg.Err != nil {
			m.Toast = ToastMsg{Kind: ToastError, Text: msg.Err.Error(), TTL: 3 * time.Second}
		}
		m.markDirty()
		return m, batch()
	case flows.APIKeySubmittedMsg:
		if msg.Err != nil {
			m.withTopAPIKeyPrompt(func(p *flows.APIKeyPrompt) { p.SetError(msg.Err) })
			m.markDirty()
			return m, batch()
		}
		m.closeModal()
		return m, batch()
	case flows.UserRoleSelectedMsg:
		m.closeModal()
		return m, batch(m.userRoleCmd(msg.Member, msg.Role))
	case ToastMsg:
		m.Toast = msg
		return m, batch()
	case tea.KeyMsg:
		return m.updateKey(msg)
	default:
		return m, batch()
	}
}

func (m Model) View() string {
	trace := traceStart("view", "")
	defer traceDone("view", trace, m.Width, m.Height)
	key := m.viewKey()
	if m.viewCache != nil && m.viewCache.valid && m.viewCache.key == key {
		return m.viewCache.value
	}
	parts := []string{
		m.renderTopBar(),
		m.renderChat(),
		m.renderInput(),
	}
	if m.Regions.TypingFooter.Height > 0 {
		parts = append(parts, m.renderTypingFooter())
	}
	parts = append(parts, m.renderStatusBar())
	body := strings.Join(parts, "\n")
	if m.Modals.Len() > 0 {
		body = m.Modals.Render(body, m.Regions)
	}
	if m.viewCache != nil {
		m.viewCache.key = key
		m.viewCache.value = body
		m.viewCache.valid = true
	}
	return body
}

func (m Model) updateKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	if m.Modals.Len() > 0 {
		switch msg.String() {
		case "ctrl+c", "ctrl+q":
			return m, tea.Quit
		case "esc":
			m.closeModal()
			return m, nil
		case "backspace":
			if handled, cmd := m.updateTopModal(msg); handled {
				m.markDirty()
				return m, cmd
			}
			m.backspaceModal()
			return m, nil
		case "enter":
			if top, ok := m.Modals.Top(); ok && top.Kind == ModalPalette && top.Input != "" {
				return m, m.submitModalInput()
			}
			if handled, cmd := m.updateTopModal(msg); handled {
				m.markDirty()
				return m, cmd
			}
			return m, m.submitModalInput()
		default:
			if handled, cmd := m.updateTopModal(msg); handled {
				m.markDirty()
				return m, cmd
			}
			if msg.Type == tea.KeyRunes {
				m.Modals.UpdateTopInput(string(msg.Runes))
			}
			return m, nil
		}
	}
	if m.Focus.Target == FocusUsers {
		switch msg.String() {
		case "up", "down", "k", "j":
			if m.Users != nil {
				m.Users.Update(msg, m.Regions.Users.Height)
				m.markDirty()
			}
			return m, nil
		case "a", "d", "x", "p", "r", "enter":
			return m, m.handleUsersKey(msg)
		}
	}
	switch msg.String() {
	case "ctrl+c", "ctrl+q":
		return m, tea.Quit
	case "ctrl+u":
		return m, m.toggleUsers()
	case "ctrl+j":
		m.setFocus(FocusChat)
		return m, nil
	case "ctrl+i", "esc":
		m.setFocus(FocusInput)
		return m, nil
	case "pgup":
		if m.Focus.Target == FocusChat {
			m.ChatScrollAnchor = maxInt(0, m.ChatScrollAnchor-m.Regions.Chat.Height)
		}
		return m, nil
	case "pgdown":
		if m.Focus.Target == FocusChat {
			m.ChatScrollAnchor += maxInt(1, m.Regions.Chat.Height)
		}
		return m, nil
	case "home":
		if m.Focus.Target == FocusChat {
			m.ChatScrollAnchor = 0
		}
		return m, nil
	case "end":
		if m.Focus.Target == FocusChat {
			m.ChatScrollAnchor = 1 << 30
		}
		return m, nil
	case "backspace":
		if m.backspaceInput() {
			return m, emitApp(flows.LocalInputChangedMsg{})
		}
		return m, nil
	case "enter":
		return m, m.submitInput()
	}
	if msg.Type != tea.KeyRunes {
		return m, nil
	}
	text := string(msg.Runes)
	if text == "/" && strings.TrimSpace(m.Input) == "" && m.Focus.Target != FocusChat {
		m.openModal(ModalPalette, newCommandPalette())
		return m, nil
	}
	if m.Focus.Target == FocusInput || m.Focus.Target == FocusIntro {
		m.Input += text
		m.closeIntro()
		m.relayout()
		return m, emitApp(flows.LocalInputChangedMsg{})
	}
	return m, nil
}

func (m *Model) resize(width, height int) {
	m.Width = maxInt(0, width)
	m.Height = maxInt(0, height)
	if m.Width < 100 && m.UsersOpen {
		m.UsersOpen = false
		m.Toast = ToastMsg{Kind: ToastWarning, Text: "users hidden: terminal too narrow", TTL: 3 * time.Second}
		if m.Focus.Target == FocusUsers {
			m.setFocus(FocusInput)
		}
	}
	m.relayout()
}

func (m *Model) relayout() {
	m.Regions = ComputeRegionsWithUsers(m.Width, m.Height, m.inputRows(), m.UsersOpen, m.typingFooterRows())
}

func (m Model) typingFooterRows() int {
	if m.State == nil || widgets.TypingFooterText(*m.State) == "" {
		return 0
	}
	return 1
}

func (m *Model) inputRows() int {
	lines := 1
	if m.Input != "" {
		lines = strings.Count(m.Input, "\n") + 1
	}
	return clampInt(lines, 1, 8)
}

func (m *Model) setFocus(target FocusTarget) {
	if target == FocusModal && m.Modals.Len() == 0 {
		target = FocusInput
	}
	m.Focus = m.Focus.WithTarget(target)
}

func (m *Model) openModal(kind ModalKind, payload any) {
	if kind == ModalPalette && payload == nil {
		payload = newCommandPalette()
	}
	m.Modals.Push(Modal{Kind: kind, Payload: payload})
	m.setFocus(FocusModal)
}

func newCommandPalette() *widgets.Palette {
	tm := theme.DarkWithCapability(theme.DetectCapability())
	return widgets.NewPalette(tm, commands.NewRegistry())
}

func (m Model) openModalCmd(kind ModalKind, payload any) tea.Cmd {
	switch kind {
	case ModalCost:
		if payload, ok := payload.(flows.CostPayload); ok && payload.Loading {
			return flows.FetchCostModalCmd(m.rpc)
		}
	case ModalProviderPicker:
		if _, ok := payload.(*flows.ProviderPicker); ok {
			return flows.FetchProvidersCmd(m.rpc)
		}
	case ModalSessionPicker:
		if _, ok := payload.(*flows.SessionPicker); ok {
			return flows.FetchSessionsCmd(m.rpc)
		}
	}
	return nil
}

func (m *Model) closeModal() {
	if modal, ok := m.Modals.Pop(); ok {
		if cleaner, ok := modal.Payload.(ModalPayloadCleaner); ok {
			cleaner.Clear()
		}
		if m.Modals.Len() == 0 {
			m.setFocus(FocusInput)
		}
	}
}

func (m *Model) updateTopModal(msg tea.KeyMsg) (bool, tea.Cmd) {
	top, ok := m.Modals.Top()
	if !ok {
		return false, nil
	}
	switch payload := top.Payload.(type) {
	case *flows.ProviderPicker:
		return true, payload.Update(msg)
	case *flows.SessionPicker:
		return true, payload.Update(msg)
	case *flows.RolePicker:
		return true, payload.Update(msg)
	case *flows.APIKeyPrompt:
		return true, payload.Update(msg, m.rpc)
	case *widgets.Palette:
		return true, payload.Update(msg)
	default:
		return false, nil
	}
}

func (m *Model) submitInput() tea.Cmd {
	input := strings.TrimSpace(m.Input)
	m.Input = ""
	m.relayout()
	return m.dispatchCommandInput(input)
}

func (m *Model) submitModalInput() tea.Cmd {
	top, ok := m.Modals.Top()
	if !ok || top.Kind != ModalPalette {
		return nil
	}
	input := strings.TrimSpace(top.Input)
	if input != "" && !strings.HasPrefix(input, "/") {
		input = "/" + input
	}
	m.closeModal()
	return m.dispatchCommandInput(input)
}

func (m *Model) dispatchCommandInput(input string) tea.Cmd {
	input = strings.TrimSpace(input)
	if input == "" {
		return nil
	}
	if !strings.HasPrefix(input, "/") {
		return emitApp(widgets.SubmitMsg{Text: input})
	}
	switch input {
	case "/cost":
		m.openModal(ModalCost, flows.CostPayload{Loading: true})
		return flows.FetchCostModalCmd(m.rpc)
	case "/provider", "/model":
		m.openModal(ModalProviderPicker, flows.NewProviderPicker(m.providerName(), m.providerModel()))
		return flows.FetchProvidersCmd(m.rpc)
	case "/session":
		m.openModal(ModalSessionPicker, flows.NewSessionPicker(m.sessionID()))
		return flows.FetchSessionsCmd(m.rpc)
	case "/users":
		return m.toggleUsers()
	case "/quit", "/exit":
		return tea.Quit
	default:
		m.Toast = ToastMsg{Kind: ToastWarning, Text: "unknown command", TTL: 2 * time.Second}
		return nil
	}
}

func (m *Model) withTopProviderPicker(fn func(*flows.ProviderPicker)) {
	m.Modals.UpdateTopPayload(func(payload any) any {
		if p, ok := payload.(*flows.ProviderPicker); ok {
			fn(p)
		}
		return payload
	})
}

func (m *Model) withTopSessionPicker(fn func(*flows.SessionPicker)) {
	m.Modals.UpdateTopPayload(func(payload any) any {
		if p, ok := payload.(*flows.SessionPicker); ok {
			fn(p)
		}
		return payload
	})
}

func (m *Model) withTopCostPayload(fn func(*flows.CostPayload)) {
	m.Modals.UpdateTopPayload(func(payload any) any {
		if p, ok := payload.(flows.CostPayload); ok {
			fn(&p)
			return p
		}
		if p, ok := payload.(*flows.CostPayload); ok {
			fn(p)
			return p
		}
		return payload
	})
}

func (m *Model) withTopAPIKeyPrompt(fn func(*flows.APIKeyPrompt)) {
	m.Modals.UpdateTopPayload(func(payload any) any {
		if p, ok := payload.(*flows.APIKeyPrompt); ok {
			fn(p)
		}
		return payload
	})
}

func (m *Model) dispatchState(action state.Action) {
	if m.Store != nil {
		m.Store.Dispatch(action)
		next := m.Store.Snapshot()
		m.State = &next
		if m.Chat != nil {
			m.Chat.SetMultiplayer(next.Multiplayer)
			m.Chat.SetMessages(next.Messages)
		}
		if m.Users != nil {
			m.Users.SetState(next.Multiplayer)
		}
		m.relayout()
		return
	}
	if m.State == nil {
		next := state.Reduce(state.AppState{}, action)
		m.State = &next
		return
	}
	next := state.Reduce(*m.State, action)
	m.State = &next
	m.relayout()
}

func (m Model) currentProviderInfo() protocol.ProviderInfo {
	return protocol.ProviderInfo{Name: m.providerName(), Model: m.providerModel(), Capabilities: m.providerCaps()}
}

func (m Model) providerName() string {
	if m.State == nil {
		return ""
	}
	return m.State.Provider.Name
}

func (m Model) providerModel() string {
	if m.State == nil {
		return ""
	}
	return m.State.Provider.Model
}

func (m Model) providerCaps() map[string]any {
	if m.State == nil || m.State.Provider.Caps == nil {
		return nil
	}
	out := make(map[string]any, len(m.State.Provider.Caps))
	for k, v := range m.State.Provider.Caps {
		out[k] = v
	}
	return out
}

func (m Model) sessionID() string {
	if m.State == nil {
		return ""
	}
	return m.State.Session.ID
}

func convertCheckpoints(checkpoints []protocol.Checkpoint) []state.Checkpoint {
	out := make([]state.Checkpoint, len(checkpoints))
	for i, checkpoint := range checkpoints {
		out[i] = state.Checkpoint{
			ID:          checkpoint.CheckpointID,
			CreatedAt:   checkpoint.CreatedAt,
			Description: checkpoint.Description,
		}
	}
	return out
}

func flowSessionID(session protocol.SessionSummary) string {
	if session.SessionID != "" {
		return session.SessionID
	}
	return session.ID
}

func (m *Model) restoreFocusAfterModalPop() {
	if m.Modals.Len() == 0 {
		m.setFocus(FocusInput)
	}
}

func (m *Model) closeIntro() {
	if !m.Intro.Active {
		return
	}
	m.Intro.Active = false
	if m.Focus.Target == FocusIntro {
		m.setFocus(FocusInput)
	}
}

func (m *Model) backspaceInput() bool {
	if m.Input == "" || (m.Focus.Target != FocusInput && m.Focus.Target != FocusIntro) {
		return false
	}
	runes := []rune(m.Input)
	m.Input = string(runes[:len(runes)-1])
	m.relayout()
	return true
}

func (m *Model) backspaceModal() {
	if m.Modals.Len() == 0 {
		return
	}
	top, ok := m.Modals.Pop()
	if !ok || top.Input == "" {
		if ok {
			m.Modals.Push(top)
		}
		return
	}
	runes := []rune(top.Input)
	top.Input = string(runes[:len(runes)-1])
	m.Modals.Push(top)
}

func (m *Model) toggleUsers() tea.Cmd {
	if m.UsersOpen {
		m.UsersOpen = false
		if m.Focus.Target == FocusUsers {
			m.setFocus(FocusInput)
		}
		m.relayout()
		return nil
	}
	if m.Width < 100 {
		m.Toast = ToastMsg{Kind: ToastWarning, Text: "users hidden: terminal too narrow", TTL: 3 * time.Second}
		return nil
	}
	if m.State == nil || !m.State.Multiplayer.Enabled {
		m.Toast = ToastMsg{Kind: ToastWarning, Text: "multiplayer disabled", TTL: 3 * time.Second}
		return nil
	}
	m.UsersOpen = true
	m.setFocus(FocusUsers)
	m.relayout()
	if m.usersFlow != nil {
		return m.usersFlow.RefreshCmd()
	}
	return nil
}

func (m *Model) handleUsersKey(msg tea.KeyMsg) tea.Cmd {
	if m.Users == nil {
		return nil
	}
	member, ok := m.Users.CurrentMember()
	if !ok {
		m.Toast = ToastMsg{Kind: ToastWarning, Text: "no user selected", TTL: 3 * time.Second}
		return nil
	}
	switch msg.String() {
	case "a":
		if m.usersFlow != nil {
			return m.usersFlow.Approve(member)
		}
	case "d":
		if m.usersFlow != nil {
			return m.usersFlow.Deny(member)
		}
	case "x":
		if m.usersFlow != nil {
			return m.usersFlow.Kick(member)
		}
	case "p":
		if m.usersFlow != nil {
			return m.usersFlow.Pass(member)
		}
	case "enter":
		if m.prompterCount() > 1 {
			return nil
		}
		if m.usersFlow != nil {
			return m.usersFlow.Pass(member)
		}
	case "r":
		m.openModal(ModalRolePicker, flows.NewRolePicker(member))
	}
	return nil
}

func (m Model) prompterCount() int {
	if m.State == nil {
		return 0
	}
	count := 0
	for _, member := range m.State.Multiplayer.Members {
		if member.Role == "prompter" {
			count++
		}
	}
	return count
}

func (m *Model) userRoleCmd(member state.Member, role string) tea.Cmd {
	if m.usersFlow == nil {
		return nil
	}
	return m.usersFlow.SetRole(member, role)
}

func (m *Model) markDirty() {
	m.uiRevision++
	if m.viewCache != nil {
		m.viewCache.valid = false
	}
}

func (m Model) viewKey() modelViewKey {
	var stateRevision uint64
	if m.State != nil {
		stateRevision = m.State.Revision
	}
	return modelViewKey{
		stateRevision:   stateRevision,
		uiRevision:      m.uiRevision,
		width:           m.Width,
		height:          m.Height,
		regions:         m.Regions,
		focus:           m.Focus.Target,
		input:           m.Input,
		chatScroll:      m.ChatScrollAnchor,
		toastText:       m.Toast.Text,
		toastKind:       m.Toast.Kind,
		introActive:     m.Intro.Active,
		introVersion:    m.Intro.Version,
		usersOpen:       m.UsersOpen,
		modalSignature:  m.modalSignature(),
		typingFooterRow: m.Regions.TypingFooter.Height,
	}
}

func (m Model) modalSignature() string {
	if len(m.Modals) == 0 {
		return ""
	}
	var b strings.Builder
	for _, modal := range m.Modals {
		b.WriteString(fmt.Sprintf("%d:%s:%T:%p;", modal.Kind, modal.Input, modal.Payload, modalPayloadPtr(modal.Payload)))
	}
	return b.String()
}

func modalPayloadPtr(payload any) any {
	switch p := payload.(type) {
	case *flows.ProviderPicker:
		return p
	case *flows.SessionPicker:
		return p
	case *flows.RolePicker:
		return p
	case *flows.APIKeyPrompt:
		return p
	case *flows.CostPayload:
		return p
	default:
		return nil
	}
}

func (m Model) renderTopBar() string {
	return renderBlock(m.Regions.TopBar, m.topBarText())
}

func (m Model) topBarText() string {
	if m.Intro.Active || m.State == nil || m.State.Connection.Phase == state.Starting {
		return EmptyStateFor(EmptyConnecting).Text
	}
	switch m.State.Connection.Phase {
	case state.Disconnected, state.Error:
		return EmptyStateFor(EmptyDisconnected).Text
	}
	provider := strings.TrimSpace(m.providerName())
	if provider == "" {
		provider = "anthropic"
	}
	return "gocli-poor · connected · " + provider
}

func (m Model) renderChat() string {
	if m.Intro.Active {
		return m.renderTranscript(m.Intro.View())
	}
	if m.Chat == nil {
		return m.renderTranscript("")
	}
	return m.renderTranscript(m.Chat.View(m.Regions.Chat.Width, m.Regions.Chat.Height))
}

func (m Model) renderTranscript(text string) string {
	chat := renderBlock(m.Regions.Chat, text)
	if !m.UsersOpen || m.Regions.Users.Width == 0 || m.Users == nil {
		return chat
	}
	users := m.Users.View(m.Regions.Users.Width, m.Regions.Users.Height)
	chatLines := strings.Split(chat, "\n")
	userLines := strings.Split(users, "\n")
	out := make([]string, m.Regions.Chat.Height)
	for i := range out {
		left := ""
		if i < len(chatLines) {
			left = chatLines[i]
		}
		right := ""
		if i < len(userLines) {
			right = userLines[i]
		}
		out[i] = fitLine(left, m.Regions.Chat.Width) + " " + fitLine(right, m.Regions.Users.Width)
	}
	return strings.Join(out, "\n")
}

func (m Model) renderInput() string {
	value := m.Input
	if value == "" {
		value = "› ·"
	} else {
		value = "› " + value
	}
	return renderBlock(m.Regions.Input, value)
}

func (m Model) renderTypingFooter() string {
	if m.State == nil {
		return renderBlock(m.Regions.TypingFooter, "")
	}
	return renderBlock(m.Regions.TypingFooter, widgets.TypingFooterView(*m.State, m.Regions.TypingFooter.Width, nil))
}

func (m Model) renderStatusBar() string {
	text := "ready"
	if m.Toast.Text != "" {
		text = m.Toast.Text
	} else if m.State != nil && len(m.State.Toasts) > 0 {
		text = m.State.Toasts[len(m.State.Toasts)-1].Text
	} else if m.State != nil && m.State.InFlight != nil {
		msg := m.progressMessage()
		if msg == "" {
			msg = "thinking"
		}
		text = "· " + msg + "…"
	}
	return renderBlock(m.Regions.StatusBar, text)
}

func (m Model) progressMessage() string {
	if m.State == nil || m.State.Progress == nil {
		return ""
	}
	return strings.TrimSpace(m.State.Progress.Message)
}

type stateUpdatedMsg struct {
	State state.AppState
}

func waitStateUpdate(ch <-chan state.AppState) tea.Cmd {
	if ch == nil {
		return nil
	}
	return func() tea.Msg {
		st, ok := <-ch
		if !ok {
			return nil
		}
		return stateUpdatedMsg{State: st}
	}
}

func renderBlock(rect Rect, text string) string {
	if rect.Height == 0 {
		return ""
	}
	lines := strings.Split(text, "\n")
	out := make([]string, rect.Height)
	for i := range out {
		line := ""
		if i < len(lines) {
			line = lines[i]
		}
		out[i] = fitLine(line, rect.Width)
	}
	return strings.Join(out, "\n")
}

func fitLine(line string, width int) string {
	if width <= 0 {
		return ""
	}
	if lipgloss.Width(line) > width {
		runes := []rune(line)
		for lipgloss.Width(string(runes)) > width && len(runes) > 0 {
			runes = runes[:len(runes)-1]
		}
		line = string(runes)
	}
	return line + spaces(width-lipgloss.Width(line))
}

func introTimeoutCmd() tea.Cmd {
	return tea.Tick(500*time.Millisecond, func(time.Time) tea.Msg {
		return IntroDoneMsg{}
	})
}

func (m Model) startFlowsCmd() tea.Cmd {
	if m.registry == nil {
		return nil
	}
	return func() tea.Msg {
		if err := m.registry.StartAll(context.Background(), flows.Deps{RPC: m.rpc, Store: m.Store, State: m.Store}); err != nil {
			return ToastMsg{Kind: ToastError, Text: err.Error(), TTL: 3 * time.Second}
		}
		return nil
	}
}

func emitApp(msg tea.Msg) tea.Cmd {
	return func() tea.Msg { return msg }
}

type IntroModel struct {
	Active  bool
	Version string
}

func (m IntroModel) View() string {
	if m.Version == "" {
		m.Version = defaultIntroVersion
	}
	return EmptyStateFor(EmptyConnecting).Text
}
