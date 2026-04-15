package commands

import (
	"sort"
	"strings"
	"sync"

	"github.com/sahilm/fuzzy"
)

type Origin string

const (
	OriginBuiltin Origin = "builtin"
	OriginCustom  Origin = "custom"
	Builtin       Origin = OriginBuiltin
	Custom        Origin = OriginCustom
)

type Command struct {
	ID          string
	Label       string
	Description string
	Usage       string
	Origin      Origin
	RequiresArg bool
}

type Registry struct {
	mu       sync.RWMutex
	builtins []Command
	customs  []Command
}

func NewRegistry() *Registry {
	return &Registry{builtins: normalizeCommands(OriginBuiltin, builtinCommands())}
}

func (r *Registry) Register(cmds ...Command) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.builtins = append(r.builtins, normalizeCommands(OriginBuiltin, cmds)...)
}

func (r *Registry) Builtins() []Command {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return cloneCommands(r.builtins)
}

func (r *Registry) SetCustoms(cmds []Command) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.customs = normalizeCommands(OriginCustom, cmds)
}

func (r *Registry) All() []Command {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]Command, 0, len(r.builtins)+len(r.customs))
	out = append(out, r.builtins...)
	out = append(out, r.customs...)
	return cloneCommands(out)
}

func (r *Registry) Filter(prefix string) []Command {
	query := filterQuery(prefix)
	all := r.All()
	if query == "" || query == "/" {
		return all
	}
	needle := strings.TrimPrefix(query, "/")
	seen := make(map[int]bool, len(all))
	var exact []Command
	var contains []Command
	for i, cmd := range all {
		id := strings.ToLower(cmd.ID)
		idBare := strings.TrimPrefix(id, "/")
		if strings.HasPrefix(id, query) || strings.HasPrefix(idBare, needle) {
			exact = append(exact, cmd)
			seen[i] = true
			continue
		}
		if strings.Contains(id, query) || (needle != "" && strings.Contains(idBare, needle)) {
			contains = append(contains, cmd)
			seen[i] = true
		}
	}
	type fuzzyHit struct {
		cmd   Command
		score int
		index int
	}
	var data []string
	var indexes []int
	for i, cmd := range all {
		if seen[i] {
			continue
		}
		data = append(data, strings.TrimPrefix(strings.ToLower(cmd.ID), "/"))
		indexes = append(indexes, i)
	}
	var hits []fuzzyHit
	for _, match := range fuzzy.Find(needle, data) {
		hits = append(hits, fuzzyHit{cmd: all[indexes[match.Index]], score: match.Score, index: indexes[match.Index]})
	}
	sort.SliceStable(hits, func(i, j int) bool {
		if hits[i].score == hits[j].score {
			return hits[i].index < hits[j].index
		}
		return hits[i].score > hits[j].score
	})
	out := make([]Command, 0, len(exact)+len(contains)+len(hits))
	out = append(out, exact...)
	out = append(out, contains...)
	for _, hit := range hits {
		out = append(out, hit.cmd)
	}
	return out
}

func builtinCommands() []Command {
	return []Command{
		{ID: "/compact", Label: "/compact", Description: "Compact conversation history", Usage: "/compact [tier]"},
		{ID: "/clear", Label: "/clear", Description: "Clear current conversation", Usage: "/clear"},
		{ID: "/provider", Label: "/provider", Description: "Switch provider", Usage: "/provider [name]", RequiresArg: true},
		{ID: "/model", Label: "/model", Description: "Switch model", Usage: "/model [name]", RequiresArg: true},
		{ID: "/session", Label: "/session", Description: "Manage sessions", Usage: "/session [name]"},
		{ID: "/cost", Label: "/cost", Description: "Show cost dashboard", Usage: "/cost"},
		{ID: "/diff", Label: "/diff", Description: "Review pending edits", Usage: "/diff"},
		{ID: "/watch", Label: "/watch", Description: "Watch repository changes", Usage: "/watch"},
		{ID: "/users", Label: "/users", Description: "Toggle users panel", Usage: "/users"},
		{ID: "/quit", Label: "/quit", Description: "Quit poor-cli", Usage: "/quit"},
		{ID: "/exit", Label: "/exit", Description: "Quit poor-cli", Usage: "/exit"},
		{ID: "/help", Label: "/help", Description: "Show help", Usage: "/help"},
	}
}

func normalizeCommands(origin Origin, cmds []Command) []Command {
	out := make([]Command, 0, len(cmds))
	for _, cmd := range cmds {
		cmd.ID = strings.TrimSpace(cmd.ID)
		if cmd.ID == "" {
			continue
		}
		if !strings.HasPrefix(cmd.ID, "/") {
			cmd.ID = "/" + cmd.ID
		}
		if cmd.Label == "" {
			cmd.Label = cmd.ID
		}
		if cmd.Usage == "" {
			cmd.Usage = cmd.ID
		}
		if cmd.Origin == "" {
			cmd.Origin = origin
		}
		out = append(out, cmd)
	}
	return out
}

func cloneCommands(cmds []Command) []Command {
	out := make([]Command, len(cmds))
	copy(out, cmds)
	return out
}

func filterQuery(prefix string) string {
	prefix = strings.TrimSpace(prefix)
	if prefix == "" {
		return ""
	}
	prefix = strings.Fields(prefix)[0]
	prefix = strings.ToLower(prefix)
	if !strings.HasPrefix(prefix, "/") {
		prefix = "/" + prefix
	}
	return prefix
}
