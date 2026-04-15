package flows

import (
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
)

type CostModalLoadedMsg struct {
	Payload CostPayload
	Err     error
}

func FetchCostModalCmd(rpc RPCClient) tea.Cmd {
	return func() tea.Msg {
		payload, err := fetchCostPayload(rpc)
		if err != nil {
			payload.Error = err.Error()
		}
		payload.Loading = false
		return CostModalLoadedMsg{Payload: payload, Err: err}
	}
}

func fetchCostPayload(rpc RPCClient) (CostPayload, error) {
	var payload CostPayload
	if err := callRPC(rpc, protocol.MethodCostSummary, nil, &payload.Snapshot); err != nil {
		if fallback := callRPC(rpc, protocol.MethodGetSessionCost, nil, &payload.Snapshot); fallback != nil {
			return payload, err
		}
	}
	if err := callRPC(rpc, protocol.MethodGetEconomySavings, nil, &payload.Savings); err != nil {
		return payload, err
	}
	return payload, nil
}

func (p CostPayload) View(width, height int) string {
	if p.Loading {
		return "loading cost..."
	}
	if p.Error != "" {
		return fit("error: "+p.Error, max(1, width))
	}
	lines := []string{
		fmt.Sprintf("%-18s %s", "Current turn:", formatModalUSD(currentTurnUSD(p.Snapshot))),
		fmt.Sprintf("%-18s %s", "Session total:", formatModalUSD(sessionUSD(p.Snapshot))),
		"",
		"Tokens:",
		fmt.Sprintf("  %-14s %s", "Input:", commaInt(inputTokens(p.Snapshot))),
		fmt.Sprintf("  %-14s %s", "Output:", commaInt(outputTokens(p.Snapshot))),
		fmt.Sprintf("  %-14s %s", "Cache read:", commaInt(cacheReadTokens(p.Snapshot))),
		fmt.Sprintf("  %-14s %s", "Cache write:", commaInt(cacheWriteTokens(p.Snapshot))),
		"",
		"By provider:",
	}
	providers := providerCosts(p.Snapshot)
	if len(providers) == 0 {
		lines = append(lines, "  none           $0.0000")
	} else {
		for _, p := range providers {
			lines = append(lines, fmt.Sprintf("  %-14s %s", p.name, formatModalUSD(p.usd)))
		}
	}
	lines = append(lines, "", savingsLine(p.Savings, sessionUSD(p.Snapshot)))
	if height > 0 && len(lines) > height {
		footer := lines[len(lines)-1]
		lines = lines[:height]
		if height > 1 {
			lines[height-1] = footer
		}
	}
	for i := range lines {
		lines[i] = fit(lines[i], max(1, width))
	}
	return strings.Join(lines, "\n")
}

type providerCost struct {
	name string
	usd  float64
}

func providerCosts(snapshot protocol.CostSnapshot) []providerCost {
	raw := snapshot.PerProvider
	if len(raw) == 0 {
		raw = snapshot.Summary.PerProvider
	}
	out := make([]providerCost, 0, len(raw))
	for name, value := range raw {
		usd := numericCost(value)
		if name == "" || usd == 0 {
			continue
		}
		out = append(out, providerCost{name: name, usd: usd})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].usd == out[j].usd {
			return out[i].name < out[j].name
		}
		return out[i].usd > out[j].usd
	})
	return out
}

func numericCost(value any) float64 {
	switch v := value.(type) {
	case float64:
		return v
	case float32:
		return float64(v)
	case int:
		return float64(v)
	case int64:
		return float64(v)
	case json.Number:
		f, _ := v.Float64()
		return f
	case map[string]any:
		return firstNonZeroFloat(anyFloat(v["cost_usd"]), anyFloat(v["costUSD"]), anyFloat(v["usd"]), anyFloat(v["cost"]))
	default:
		return 0
	}
}

func currentTurnUSD(snapshot protocol.CostSnapshot) float64 {
	for _, m := range []map[string]any{snapshot.LastTurn, snapshot.LastTurnCamel} {
		if v := firstNonZeroFloat(anyFloat(m["cost_usd"]), anyFloat(m["costUSD"]), anyFloat(m["cost"])); v != 0 {
			return v
		}
	}
	turns := snapshot.PerTurn
	if len(turns) == 0 {
		turns = snapshot.PerTurnCamel
	}
	if len(turns) == 0 {
		return 0
	}
	last := turns[len(turns)-1]
	return firstNonZeroFloat(anyFloat(last["cost_usd"]), anyFloat(last["costUSD"]), anyFloat(last["cost"]))
}

func sessionUSD(snapshot protocol.CostSnapshot) float64 {
	return firstNonZeroFloat(snapshot.Session.TotalUSD, snapshot.SessionCost, snapshot.Summary.SessionCost, snapshot.TotalCost, snapshot.Summary.TotalCost, snapshot.Summary.EstimatedCostUSD, snapshot.Summary.EstimatedCost)
}

func inputTokens(snapshot protocol.CostSnapshot) int {
	return firstNonZero(snapshot.InputTokens, snapshot.Summary.InputTokens, snapshot.Summary.InputTokensCamel, snapshot.Session.TotalTokens["in"])
}

func outputTokens(snapshot protocol.CostSnapshot) int {
	return firstNonZero(snapshot.OutputTokens, snapshot.Summary.OutputTokens, snapshot.Summary.OutputTokensCamel, snapshot.Session.TotalTokens["out"])
}

func cacheReadTokens(snapshot protocol.CostSnapshot) int {
	return firstNonZero(snapshot.CacheReadTokens, snapshot.Summary.CacheReadTokens, snapshot.Summary.CacheReadInputTokens, snapshot.Summary.CacheReadInputTokensCamel, snapshot.Session.TotalTokens["cached_read"])
}

func cacheWriteTokens(snapshot protocol.CostSnapshot) int {
	return firstNonZero(snapshot.CacheWriteTokens, snapshot.Summary.CacheWriteTokens, snapshot.Summary.CacheCreationInputTokens, snapshot.Summary.CacheCreationInputTokensCamel, snapshot.Session.TotalTokens["cached_write"])
}

func savingsLine(snapshot protocol.SavingsSnapshot, sessionUSD float64) string {
	usd := savingsUSD(snapshot)
	pct := 0.0
	if sessionUSD+usd > 0 {
		pct = usd / (sessionUSD + usd) * 100
	}
	return fmt.Sprintf("Savings (economy mode): %s (%.0f%%)", formatModalUSD(usd), pct)
}

func savingsUSD(snapshot protocol.SavingsSnapshot) float64 {
	return firstNonZeroFloat(snapshot.USDSaved, snapshot.TotalSavedUSD, snapshot.CostSaved, anyFloat(snapshot.SessionDelta["usd_saved"]), anyFloat(snapshot.SessionDelta["usdSaved"]), anyFloat(snapshot.SessionDelta["costSaved"]))
}

func anyFloat(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case float32:
		return float64(n)
	case int:
		return float64(n)
	case int64:
		return float64(n)
	case json.Number:
		f, _ := n.Float64()
		return f
	default:
		return 0
	}
}

func formatModalUSD(v float64) string {
	return fmt.Sprintf("$%.4f", v)
}

func commaInt(v int) string {
	s := strconv.Itoa(v)
	if len(s) <= 3 {
		return s
	}
	var b strings.Builder
	pre := len(s) % 3
	if pre == 0 {
		pre = 3
	}
	b.WriteString(s[:pre])
	for i := pre; i < len(s); i += 3 {
		b.WriteByte(',')
		b.WriteString(s[i : i+3])
	}
	return b.String()
}

func firstNonZero(values ...int) int {
	for _, value := range values {
		if value != 0 {
			return value
		}
	}
	return 0
}

func firstNonZeroFloat(values ...float64) float64 {
	for _, value := range values {
		if value != 0 {
			return value
		}
	}
	return 0
}
