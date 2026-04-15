package flows

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
)

type APIKeyPrompt struct {
	Provider string
	Input    string
	Persist  bool
	Error    string
	Message  string
}

type APIKeySubmittedMsg struct {
	Provider string
	Result   protocol.SetAPIKeyResult
	Err      error
}

func NewAPIKeyPrompt(provider, message string) *APIKeyPrompt {
	return &APIKeyPrompt{Provider: provider, Persist: true, Message: message}
}

func SetAPIKeyCmd(rpc RPCClient, provider, key string, persist bool) tea.Cmd {
	return func() tea.Msg {
		var result protocol.SetAPIKeyResult
		reload := true
		params := protocol.SetApiKeyParams{
			Provider:             provider,
			APIKey:               key,
			Persist:              &persist,
			ReloadActiveProvider: &reload,
		}
		err := callRPC(rpc, protocol.MethodSetAPIKey, params, &result)
		if err == nil && !result.Success && result.Error != "" {
			err = fmt.Errorf("%s", result.Error)
		}
		return APIKeySubmittedMsg{Provider: provider, Result: result, Err: err}
	}
}

func (p *APIKeyPrompt) Update(msg tea.KeyMsg, rpc RPCClient) tea.Cmd {
	switch msg.String() {
	case "enter":
		key := p.Input
		return SetAPIKeyCmd(rpc, p.Provider, key, p.Persist)
	case "backspace":
		p.backspace()
	case "tab", " ":
		p.Persist = !p.Persist
	default:
		if msg.Type == tea.KeyRunes {
			p.Input += string(msg.Runes)
		}
	}
	return nil
}

func (p *APIKeyPrompt) View(width, height int) string {
	width = max(24, width)
	var lines []string
	if p.Message != "" {
		lines = append(lines, fit(p.Message, width-2), "")
	}
	lines = append(lines, "Enter API key:")
	mask := strings.Repeat("*", len([]rune(p.Input)))
	if mask == "" {
		mask = "_"
	}
	lines = append(lines, fit(mask, width-2), "")
	box := "[ ]"
	if p.Persist {
		box = "[x]"
	}
	lines = append(lines, box+" save to keyring", "", "[Enter] save  [Esc] cancel")
	if p.Error != "" {
		lines = append(lines, "", fit("error: "+p.Error, width-2))
	}
	return strings.Join(lines, "\n")
}

func (p *APIKeyPrompt) SetError(err error) {
	if err == nil {
		p.Error = ""
		return
	}
	p.Error = err.Error()
}

func (p *APIKeyPrompt) Clear() {
	p.Input = ""
}

func (p *APIKeyPrompt) backspace() {
	if p.Input == "" {
		return
	}
	runes := []rune(p.Input)
	p.Input = string(runes[:len(runes)-1])
}
