package flows

import (
	"fmt"
	"sort"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
)

type SessionPicker struct {
	ActiveSessionID string
	Sessions        []protocol.SessionSummary
	Selected        int
	Loading         bool
	Error           string
}

type SessionsLoadedMsg struct {
	Result protocol.ListSessionsResult
	Err    error
}

type SessionSelectedMsg struct {
	Session protocol.SessionSummary
}

type SessionSwitchedMsg struct {
	Session protocol.SessionSummary
	Result  protocol.SwitchSessionResult
	Err     error
}

type CheckpointsLoadedMsg struct {
	SessionID string
	Result    protocol.ListCheckpointsResult
	Err       error
}

type RestoreSessionParams struct {
	SessionID    string `json:"sessionId"`
	CheckpointID string `json:"checkpointId,omitempty"`
}

type RestoreSessionResult struct {
	Session protocol.SessionSummary `json:"session,omitempty"`
	Error   string                  `json:"error,omitempty"`
}

type SessionRestoredMsg struct {
	SessionID    string
	CheckpointID string
	Result       RestoreSessionResult
	Err          error
}

func NewSessionPicker(activeSessionID string) *SessionPicker {
	return &SessionPicker{ActiveSessionID: activeSessionID, Loading: true}
}

func FetchSessionsCmd(rpc RPCClient) tea.Cmd {
	return func() tea.Msg {
		var result protocol.ListSessionsResult
		err := callRPC(rpc, protocol.MethodListSessions, nil, &result)
		return SessionsLoadedMsg{Result: result, Err: err}
	}
}

func SwitchSessionCmd(rpc RPCClient, session protocol.SessionSummary) tea.Cmd {
	return func() tea.Msg {
		var result protocol.SwitchSessionResult
		err := callRPC(rpc, protocol.MethodSwitchSession, protocol.SwitchSessionParams{SessionID: sessionID(session)}, &result)
		if err == nil && result.Error != "" {
			err = fmt.Errorf("%s", result.Error)
		}
		return SessionSwitchedMsg{Session: session, Result: result, Err: err}
	}
}

func FetchCheckpointsCmd(rpc RPCClient, sessionID string) tea.Cmd {
	return func() tea.Msg {
		var result protocol.ListCheckpointsResult
		err := callRPC(rpc, protocol.MethodListCheckpoints, map[string]string{"sessionId": sessionID}, &result)
		return CheckpointsLoadedMsg{SessionID: sessionID, Result: result, Err: err}
	}
}

func RestoreSessionCmd(rpc RPCClient, sessionID, checkpointID string) tea.Cmd {
	return func() tea.Msg {
		var result RestoreSessionResult
		params := RestoreSessionParams{SessionID: sessionID, CheckpointID: checkpointID}
		err := callRPC(rpc, protocol.MethodRestoreSession, params, &result)
		if err == nil && result.Error != "" {
			err = fmt.Errorf("%s", result.Error)
		}
		return SessionRestoredMsg{SessionID: sessionID, CheckpointID: checkpointID, Result: result, Err: err}
	}
}

func (p *SessionPicker) ApplyLoaded(msg SessionsLoadedMsg) {
	p.Loading = false
	if msg.Err != nil {
		p.Error = msg.Err.Error()
		return
	}
	p.Error = ""
	p.Sessions = append([]protocol.SessionSummary(nil), msg.Result.Sessions...)
	sort.SliceStable(p.Sessions, func(i, j int) bool {
		return p.Sessions[i].UpdatedAt > p.Sessions[j].UpdatedAt
	})
	active := p.ActiveSessionID
	if active == "" {
		active = msg.Result.ActiveSessionID
	}
	p.Selected = selectedSessionIndex(p.Sessions, active)
}

func (p *SessionPicker) Update(msg tea.KeyMsg) tea.Cmd {
	switch msg.String() {
	case "up", "ctrl+p":
		if p.Selected > 0 {
			p.Selected--
		}
	case "down", "ctrl+n":
		if p.Selected < len(p.Sessions)-1 {
			p.Selected++
		}
	case "enter":
		if len(p.Sessions) == 0 {
			return nil
		}
		return emit(SessionSelectedMsg{Session: p.Sessions[p.Selected]})
	}
	return nil
}

func (p *SessionPicker) View(width, height int) string {
	width = max(20, width)
	bodyHeight := max(1, height-2)
	if p.Loading {
		return "loading sessions..."
	}
	lines := make([]string, 0, bodyHeight)
	if p.Error != "" {
		lines = append(lines, fit("error: "+p.Error, width-2))
	}
	for i, session := range p.Sessions {
		if len(lines) >= bodyHeight {
			break
		}
		marker := " "
		if i == p.Selected {
			marker = ">"
		}
		label := sessionTitle(session)
		line := fmt.Sprintf("%s %-24s %4d msgs  %s", marker, label, session.MessageCount, session.Model)
		lines = append(lines, fit(line, width-2))
	}
	if len(lines) == 0 {
		lines = append(lines, "no sessions")
	}
	return strings.Join(lines, "\n")
}

func selectedSessionIndex(sessions []protocol.SessionSummary, id string) int {
	for i, session := range sessions {
		if sessionID(session) == id {
			return i
		}
	}
	return 0
}

func sessionTitle(session protocol.SessionSummary) string {
	for _, value := range []string{session.Title, session.Label, session.SessionID, session.ID} {
		value = strings.TrimSpace(value)
		if value != "" {
			return value
		}
	}
	return "untitled"
}

func sessionID(session protocol.SessionSummary) string {
	if session.SessionID != "" {
		return session.SessionID
	}
	return session.ID
}
