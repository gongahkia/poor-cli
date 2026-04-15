package flows

import (
	"context"
	"fmt"
	"sort"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
)

type RPCClient interface {
	Call(ctx context.Context, method string, params any, result any) error
}

type ProviderChoice struct {
	Provider string
	Model    string
	Detail   protocol.ProviderDetail
}

type ProviderPicker struct {
	ActiveProvider string
	ActiveModel    string
	Choices        []ProviderChoice
	Selected       int
	Loading        bool
	Error          string
}

type ProvidersLoadedMsg struct {
	Result protocol.ListProvidersResult
	Err    error
}

type ProviderSelectedMsg struct {
	Choice ProviderChoice
}

type ProviderSwitchedMsg struct {
	Choice   ProviderChoice
	Previous protocol.ProviderInfo
	Result   protocol.SwitchProviderResult
	Err      error
}

func NewProviderPicker(activeProvider, activeModel string) *ProviderPicker {
	return &ProviderPicker{ActiveProvider: activeProvider, ActiveModel: activeModel, Loading: true}
}

func FetchProvidersCmd(rpc RPCClient) tea.Cmd {
	return func() tea.Msg {
		var result protocol.ListProvidersResult
		err := callRPC(rpc, protocol.MethodListProviders, nil, &result)
		return ProvidersLoadedMsg{Result: result, Err: err}
	}
}

func SwitchProviderCmd(rpc RPCClient, choice ProviderChoice, previous protocol.ProviderInfo) tea.Cmd {
	return func() tea.Msg {
		var result protocol.SwitchProviderResult
		params := protocol.SwitchProviderParams{Provider: choice.Provider, Model: choice.Model}
		err := callRPC(rpc, protocol.MethodSwitchProvider, params, &result)
		if err == nil && !result.Success && result.Error != "" {
			err = fmt.Errorf("%s", result.Error)
		}
		return ProviderSwitchedMsg{Choice: choice, Previous: previous, Result: result, Err: err}
	}
}

func (p *ProviderPicker) ApplyLoaded(msg ProvidersLoadedMsg) {
	p.Loading = false
	if msg.Err != nil {
		p.Error = msg.Err.Error()
		return
	}
	p.Error = ""
	p.Choices = providerChoices(msg.Result)
	p.Selected = selectedProviderIndex(p.Choices, p.ActiveProvider, p.ActiveModel)
}

func (p *ProviderPicker) Update(msg tea.KeyMsg) tea.Cmd {
	switch msg.String() {
	case "up", "ctrl+p":
		if p.Selected > 0 {
			p.Selected--
		}
	case "down", "ctrl+n":
		if p.Selected < len(p.Choices)-1 {
			p.Selected++
		}
	case "left", "right":
		p.cycleModel(msg.String() == "right")
	case "enter":
		if len(p.Choices) == 0 {
			return nil
		}
		choice := p.Choices[p.Selected]
		return emitCommand(ProviderSelectedMsg{Choice: choice})
	}
	return nil
}

func (p *ProviderPicker) View(width, height int) string {
	width = max(20, width)
	bodyHeight := max(1, height-2)
	if p.Loading {
		return "loading providers..."
	}
	lines := make([]string, 0, bodyHeight)
	if p.Error != "" {
		lines = append(lines, fit("error: "+p.Error, width-2))
	}
	for i, choice := range p.Choices {
		if len(lines) >= bodyHeight {
			break
		}
		marker := " "
		if i == p.Selected {
			marker = ">"
		}
		status := providerStatus(choice.Detail)
		line := fmt.Sprintf("%s %-16s %-18s [%s]", marker, choice.Provider, choice.Model, status)
		lines = append(lines, fit(line, width-2))
	}
	if len(lines) == 0 {
		lines = append(lines, "no providers")
	}
	return strings.Join(lines, "\n")
}

func (p *ProviderPicker) cycleModel(next bool) {
	if len(p.Choices) == 0 || p.Selected < 0 || p.Selected >= len(p.Choices) {
		return
	}
	choice := &p.Choices[p.Selected]
	models := choice.Detail.Models
	if len(models) <= 1 {
		return
	}
	idx := 0
	for i, model := range models {
		if model == choice.Model {
			idx = i
			break
		}
	}
	if next {
		idx = (idx + 1) % len(models)
	} else {
		idx = (idx - 1 + len(models)) % len(models)
	}
	choice.Model = models[idx]
}

func providerChoices(result protocol.ListProvidersResult) []ProviderChoice {
	names := make([]string, 0, len(result))
	for name := range result {
		names = append(names, name)
	}
	sort.Strings(names)
	out := make([]ProviderChoice, 0, len(names))
	for _, name := range names {
		detail := result[name]
		model := ""
		if len(detail.Models) > 0 {
			model = detail.Models[0]
		}
		out = append(out, ProviderChoice{Provider: name, Model: model, Detail: detail})
	}
	return out
}

func selectedProviderIndex(choices []ProviderChoice, provider, model string) int {
	selected := 0
	for i, choice := range choices {
		if choice.Provider != provider {
			continue
		}
		selected = i
		if model == "" || choice.Model == model {
			break
		}
		for j := range choice.Detail.Models {
			if choice.Detail.Models[j] == model {
				choices[i].Model = model
				break
			}
		}
		break
	}
	return selected
}

func providerStatus(detail protocol.ProviderDetail) string {
	switch {
	case detail.Ready:
		return "ready"
	case !detail.Available:
		return "miss "
	default:
		return "key? "
	}
}

func callRPC(rpc RPCClient, method string, params any, result any) error {
	if rpc == nil {
		return fmt.Errorf("rpc client unavailable")
	}
	return rpc.Call(context.Background(), method, params, result)
}

func emit(msg tea.Msg) tea.Cmd {
	return func() tea.Msg {
		return msg
	}
}
