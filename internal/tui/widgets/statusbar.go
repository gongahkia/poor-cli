package widgets

import (
	"fmt"
	"sort"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/theme"
)

const (
	statusSep   = " · "
	costWarnUSD = 0.05
	costBadUSD  = 0.25
	ctxWarnPct  = 70.0
	ctxBadPct   = 90.0
)

type StatusBarDeps struct {
	Store *state.Store
	Theme *theme.Theme
}

type StatusBar struct {
	theme       theme.Theme
	snapshot    state.AppState
	updates     <-chan state.AppState
	unsubscribe func()
}

type statusSlot struct {
	id    string
	text  string
	style lipgloss.Style
}

func NewStatusBar(d StatusBarDeps) *StatusBar {
	t := defaultTheme(d.Theme)
	b := &StatusBar{theme: t}
	if d.Store != nil {
		b.updates, b.unsubscribe = d.Store.Subscribe()
		b.snapshot = d.Store.Snapshot()
	}
	return b
}

func (b *StatusBar) Close() {
	if b.unsubscribe != nil {
		b.unsubscribe()
		b.unsubscribe = nil
	}
}

func (b *StatusBar) View(width int) string {
	b.sync()
	return fitLine(b.render(width), width)
}

func (b *StatusBar) TypingFooterView(width int) string {
	b.sync()
	return TypingFooterView(b.snapshot, width, &b.theme)
}

func (b *StatusBar) sync() {
	for b.updates != nil {
		select {
		case snapshot, ok := <-b.updates:
			if !ok {
				b.updates = nil
				return
			}
			b.snapshot = snapshot
		default:
			return
		}
	}
}

func (b StatusBar) render(width int) string {
	if width <= 0 {
		return ""
	}
	slots := b.slots()
	for _, id := range []string{"tokens", "context", "session", "conn"} {
		if slotsWidth(slots) <= width {
			return renderSlots(slots)
		}
		slots = dropSlot(slots, id)
	}
	if slotsWidth(slots) <= width {
		return renderSlots(slots)
	}
	return b.renderMandatory(width)
}

func TypingFooterView(snapshot state.AppState, width int, t *theme.Theme) string {
	text := TypingFooterText(snapshot)
	if text == "" || width <= 0 {
		return ""
	}
	tm := defaultTheme(t)
	return fitLine(tm.Muted.Render("  "+text), width)
}

func TypingFooterText(snapshot state.AppState) string {
	mp := snapshot.Multiplayer
	if !mp.Enabled || len(mp.Typing) == 0 {
		return ""
	}
	localID := strings.TrimSpace(mp.LocalConnectionID)
	if localID == "" {
		localID = "local"
	}
	names := memberNameMap(mp.Members)
	seen := map[string]struct{}{}
	typers := make([]string, 0, len(mp.Typing))
	for _, member := range mp.Members {
		id := strings.TrimSpace(member.ConnectionID)
		if id == "" || id == localID || !mp.Typing[id] {
			continue
		}
		seen[id] = struct{}{}
		typers = append(typers, displayNameFor(id, names))
	}
	rest := make([]string, 0, len(mp.Typing))
	for id, typing := range mp.Typing {
		if !typing || strings.TrimSpace(id) == "" || id == localID {
			continue
		}
		if _, ok := seen[id]; !ok {
			rest = append(rest, id)
		}
	}
	sort.Strings(rest)
	for _, id := range rest {
		typers = append(typers, displayNameFor(id, names))
	}
	switch len(typers) {
	case 0:
		return ""
	case 1:
		return typers[0] + " is typing…"
	case 2:
		return typers[0] + " and " + typers[1] + " are typing…"
	case 3:
		return typers[0] + ", " + typers[1] + ", and " + typers[2] + " are typing…"
	default:
		return typers[0] + ", " + typers[1] + ", " + typers[2] + fmt.Sprintf(" +%d typing…", len(typers)-3)
	}
}

func memberNameMap(members []state.Member) map[string]string {
	names := make(map[string]string, len(members))
	for _, member := range members {
		id := strings.TrimSpace(member.ConnectionID)
		if id == "" {
			continue
		}
		name := strings.TrimSpace(member.DisplayName)
		if name != "" {
			names[id] = strings.Join(strings.Fields(name), " ")
		}
	}
	return names
}

func displayNameFor(id string, names map[string]string) string {
	if name := names[id]; name != "" {
		return name
	}
	return id
}

func (b StatusBar) slots() []statusSlot {
	slots := make([]statusSlot, 0, 6)
	if dot := b.connSlot(); dot.text != "" {
		slots = append(slots, dot)
	}
	slots = append(slots, b.providerSlot())
	if session := b.sessionSlot(); session.text != "" {
		slots = append(slots, session)
	}
	if ctx := b.contextSlot(); ctx.text != "" {
		slots = append(slots, ctx)
	}
	if tokens := b.tokensSlot(); tokens.text != "" {
		slots = append(slots, tokens)
	}
	slots = append(slots, b.costSlot())
	return slots
}

func (b StatusBar) connSlot() statusSlot {
	style := b.theme.Error
	switch b.snapshot.Connection.Phase {
	case state.Ready:
		style = b.theme.Success
	case state.Starting:
		style = b.theme.Warning
	case state.Error, state.Disconnected:
		style = b.theme.Error
	}
	return statusSlot{id: "conn", text: "●", style: style}
}

func (b StatusBar) providerSlot() statusSlot {
	provider := strings.TrimSpace(b.snapshot.Provider.Name)
	model := strings.TrimSpace(b.snapshot.Provider.Model)
	if provider == "" {
		provider = "provider"
	}
	if model == "" {
		model = "model"
	}
	return statusSlot{id: "provider", text: provider + ":" + model, style: b.theme.StatusBarActive}
}

func (b StatusBar) sessionSlot() statusSlot {
	id := strings.TrimSpace(b.snapshot.Session.ID)
	if id == "" {
		return statusSlot{}
	}
	id = strings.TrimPrefix(id, "#")
	id = truncateText(id, 8)
	return statusSlot{id: "session", text: "session:#" + id, style: b.theme.Muted}
}

func (b StatusBar) contextSlot() statusSlot {
	pct := b.snapshot.ContextPressure.Pct
	if pct == 0 && b.snapshot.ContextPressure.Budget > 0 {
		pct = float64(b.snapshot.ContextPressure.Tokens) / float64(b.snapshot.ContextPressure.Budget)
	}
	if pct == 0 {
		return statusSlot{}
	}
	if pct <= 1 {
		pct *= 100
	}
	style := b.theme.CostGood
	if pct >= ctxBadPct {
		style = b.theme.CostBad
	} else if pct >= ctxWarnPct {
		style = b.theme.CostWarn
	}
	return statusSlot{id: "context", text: fmt.Sprintf("ctx:%.0f%%", pct), style: style}
}

func (b StatusBar) tokensSlot() statusSlot {
	cost := b.snapshot.Cost
	if cost.InputTokens == 0 && cost.OutputTokens == 0 {
		return statusSlot{}
	}
	return statusSlot{id: "tokens", text: fmt.Sprintf("tok:%d/%d", cost.InputTokens, cost.OutputTokens), style: b.theme.Muted}
}

func (b StatusBar) costSlot() statusSlot {
	cost := displayCost(b.snapshot.Cost)
	return statusSlot{id: "cost", text: formatCost(cost), style: b.costStyle(cost)}
}

func (b StatusBar) costStyle(cost float64) lipgloss.Style {
	if cost >= costBadUSD {
		return b.theme.CostBad
	}
	if cost >= costWarnUSD {
		return b.theme.CostWarn
	}
	return b.theme.CostGood
}

func (b StatusBar) renderMandatory(width int) string {
	provider := b.providerSlot()
	cost := b.costSlot()
	costWidth := lipgloss.Width(cost.text)
	if costWidth >= width {
		return cost.style.Render(truncateText(cost.text, width))
	}
	providerBudget := width - costWidth - lipgloss.Width(statusSep)
	if providerBudget <= 0 {
		return cost.style.Render(cost.text)
	}
	provider.text = truncateText(provider.text, providerBudget)
	return renderSlots([]statusSlot{provider, cost})
}

func displayCost(cost state.CostState) float64 {
	if cost.SessionTotalUSD != 0 {
		return cost.SessionTotalUSD
	}
	return cost.TotalUSD
}

func formatCost(cost float64) string {
	if cost > 0 && cost < 0.01 {
		return fmt.Sprintf("$%.4f", cost)
	}
	return fmt.Sprintf("$%.2f", cost)
}

func renderSlots(slots []statusSlot) string {
	parts := make([]string, 0, len(slots))
	for _, slot := range slots {
		if slot.text == "" {
			continue
		}
		parts = append(parts, slot.style.Render(slot.text))
	}
	return strings.Join(parts, statusSep)
}

func slotsWidth(slots []statusSlot) int {
	return lipgloss.Width(renderSlots(slots))
}

func dropSlot(slots []statusSlot, id string) []statusSlot {
	out := slots[:0]
	for _, slot := range slots {
		if slot.id != id {
			out = append(out, slot)
		}
	}
	return out
}

func fitLine(line string, width int) string {
	if width <= 0 {
		return ""
	}
	for lipgloss.Width(line) > width {
		line = truncateText(line, lipgloss.Width(line)-1)
	}
	return line + strings.Repeat(" ", width-lipgloss.Width(line))
}

func truncateText(s string, width int) string {
	if width <= 0 {
		return ""
	}
	if lipgloss.Width(s) <= width {
		return s
	}
	runes := []rune(s)
	for len(runes) > 0 && lipgloss.Width(string(runes)) > width {
		runes = runes[:len(runes)-1]
	}
	return string(runes)
}

func defaultTheme(t *theme.Theme) theme.Theme {
	if t != nil {
		return *t
	}
	return theme.Dark()
}
