package config

import (
	"fmt"

	"gopkg.in/yaml.v3"
)

type Theme struct {
	Name   string            `yaml:"name"`
	Inline map[string]string `yaml:"inline,omitempty"`
}

func (t *Theme) UnmarshalYAML(n *yaml.Node) error {
	switch n.Kind {
	case yaml.ScalarNode:
		t.Name = n.Value
		t.Inline = nil
		return nil
	case yaml.MappingNode:
		t.Name = ""
		t.Inline = map[string]string{}
		for i := 0; i < len(n.Content); i += 2 {
			k := n.Content[i]
			v := n.Content[i+1]
			if v.Kind != yaml.ScalarNode {
				return fmt.Errorf("theme.%s: expected string at line %d", k.Value, v.Line)
			}
			if k.Value == "name" {
				t.Name = v.Value
				continue
			}
			t.Inline[k.Value] = v.Value
		}
		if len(t.Inline) == 0 {
			t.Inline = nil
		}
		return nil
	case yaml.AliasNode:
		return t.UnmarshalYAML(n.Alias)
	case 0:
		return nil
	default:
		return fmt.Errorf("theme: expected string or map at line %d", n.Line)
	}
}

type Config struct {
	Theme               Theme             `yaml:"theme"`
	ServerPath          string            `yaml:"server_path"`
	DefaultProvider     string            `yaml:"default_provider"`
	DefaultModel        string            `yaml:"default_model"`
	ContextBudgetTokens int               `yaml:"context_budget_tokens"`
	MaxResponseTokens   int               `yaml:"max_response_tokens"`
	AutoAcceptSafeEdits bool              `yaml:"auto_accept_safe_edits"`
	HistoryFile         string            `yaml:"history_file"`
	LogLevel            string            `yaml:"log_level"`
	Keybindings         map[string]string `yaml:"keybindings"`
}
