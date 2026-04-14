package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

type partialConfig struct {
	Theme               *Theme            `yaml:"theme"`
	ServerPath          *string           `yaml:"server_path"`
	DefaultProvider     *string           `yaml:"default_provider"`
	DefaultModel        *string           `yaml:"default_model"`
	ContextBudgetTokens *int              `yaml:"context_budget_tokens"`
	MaxResponseTokens   *int              `yaml:"max_response_tokens"`
	AutoAcceptSafeEdits *bool             `yaml:"auto_accept_safe_edits"`
	HistoryFile         *string           `yaml:"history_file"`
	LogLevel            *string           `yaml:"log_level"`
	Keybindings         map[string]string `yaml:"keybindings"`
}

type fileMeta struct {
	path          string
	fieldLines    map[string]int
	keybindLines  map[string]int
	keybindSource map[string]bool
}

type envMeta struct {
	fields      map[string]bool
	keybindings map[string]bool
}

func Load() (*Config, error) {
	cfg := DefaultConfig()
	path, err := configPath()
	if err != nil {
		return nil, err
	}
	meta := fileMeta{}
	if path != "" {
		meta, err = mergeFile(cfg, path)
		if err != nil {
			return nil, err
		}
	}
	env, err := applyEnv(cfg)
	if err != nil {
		return nil, err
	}
	if err := validateConfig(cfg, meta, env); err != nil {
		return nil, err
	}
	return cfg, nil
}

func configPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	var paths []string
	if xdg := os.Getenv("XDG_CONFIG_HOME"); xdg != "" {
		paths = append(paths, filepath.Join(xdg, "gocli-poor", "config.yaml"))
	}
	paths = append(paths,
		filepath.Join(home, ".config", "gocli-poor", "config.yaml"),
		filepath.Join(home, ".gocli-poor.yaml"),
	)
	for _, p := range paths {
		info, err := os.Stat(p)
		if err == nil && !info.IsDir() {
			return p, nil
		}
		if err != nil && !errors.Is(err, os.ErrNotExist) {
			return "", err
		}
	}
	return "", nil
}

func mergeFile(cfg *Config, path string) (fileMeta, error) {
	f, err := os.Open(path)
	if err != nil {
		return fileMeta{}, err
	}
	defer f.Close()
	var root yaml.Node
	if err := yaml.NewDecoder(f).Decode(&root); err != nil {
		return fileMeta{}, fmt.Errorf("%s: %w", path, err)
	}
	meta := collectMeta(path, &root)
	if len(root.Content) == 0 {
		return meta, nil
	}
	var p partialConfig
	if err := root.Content[0].Decode(&p); err != nil {
		return fileMeta{}, fmt.Errorf("%s: %w", path, err)
	}
	mergePartial(cfg, p)
	return meta, nil
}

func collectMeta(path string, root *yaml.Node) fileMeta {
	meta := fileMeta{path: path, fieldLines: map[string]int{}, keybindLines: map[string]int{}, keybindSource: map[string]bool{}}
	if len(root.Content) == 0 || root.Content[0].Kind != yaml.MappingNode {
		return meta
	}
	n := root.Content[0]
	for i := 0; i < len(n.Content); i += 2 {
		k := n.Content[i]
		v := n.Content[i+1]
		meta.fieldLines[k.Value] = k.Line
		if k.Value != "keybindings" || v.Kind != yaml.MappingNode {
			continue
		}
		for j := 0; j < len(v.Content); j += 2 {
			kk := v.Content[j]
			meta.keybindLines[kk.Value] = kk.Line
			meta.keybindSource[kk.Value] = true
		}
	}
	return meta
}

func mergePartial(cfg *Config, p partialConfig) {
	if p.Theme != nil {
		cfg.Theme = *p.Theme
	}
	if p.ServerPath != nil {
		cfg.ServerPath = *p.ServerPath
	}
	if p.DefaultProvider != nil {
		cfg.DefaultProvider = *p.DefaultProvider
	}
	if p.DefaultModel != nil {
		cfg.DefaultModel = *p.DefaultModel
	}
	if p.ContextBudgetTokens != nil {
		cfg.ContextBudgetTokens = *p.ContextBudgetTokens
	}
	if p.MaxResponseTokens != nil {
		cfg.MaxResponseTokens = *p.MaxResponseTokens
	}
	if p.AutoAcceptSafeEdits != nil {
		cfg.AutoAcceptSafeEdits = *p.AutoAcceptSafeEdits
	}
	if p.HistoryFile != nil {
		cfg.HistoryFile = *p.HistoryFile
	}
	if p.LogLevel != nil {
		cfg.LogLevel = *p.LogLevel
	}
	for action, binding := range p.Keybindings {
		cfg.Keybindings[action] = binding
	}
}

func applyEnv(cfg *Config) (envMeta, error) {
	meta := envMeta{fields: map[string]bool{}, keybindings: map[string]bool{}}
	if v := os.Getenv("POOR_CLI_SERVER_PATH"); v != "" {
		cfg.ServerPath = v
		meta.fields["server_path"] = true
	}
	if stringEnv("GOCLI_POOR_THEME", func(v string) { cfg.Theme = Theme{Name: v} }) {
		meta.fields["theme"] = true
	}
	if stringEnv("GOCLI_POOR_SERVER_PATH", func(v string) { cfg.ServerPath = v }) {
		meta.fields["server_path"] = true
	}
	if stringEnv("GOCLI_POOR_DEFAULT_PROVIDER", func(v string) { cfg.DefaultProvider = v }) {
		meta.fields["default_provider"] = true
	}
	if stringEnv("GOCLI_POOR_DEFAULT_MODEL", func(v string) { cfg.DefaultModel = v }) {
		meta.fields["default_model"] = true
	}
	if stringEnv("GOCLI_POOR_HISTORY_FILE", func(v string) { cfg.HistoryFile = v }) {
		meta.fields["history_file"] = true
	}
	if stringEnv("GOCLI_POOR_LOG_LEVEL", func(v string) { cfg.LogLevel = v }) {
		meta.fields["log_level"] = true
	}
	if err := intEnv("GOCLI_POOR_CONTEXT_BUDGET_TOKENS", func(v int) { cfg.ContextBudgetTokens = v }); err != nil {
		return meta, err
	} else if os.Getenv("GOCLI_POOR_CONTEXT_BUDGET_TOKENS") != "" {
		meta.fields["context_budget_tokens"] = true
	}
	if err := intEnv("GOCLI_POOR_MAX_RESPONSE_TOKENS", func(v int) { cfg.MaxResponseTokens = v }); err != nil {
		return meta, err
	} else if os.Getenv("GOCLI_POOR_MAX_RESPONSE_TOKENS") != "" {
		meta.fields["max_response_tokens"] = true
	}
	if err := boolEnv("GOCLI_POOR_AUTO_ACCEPT_SAFE_EDITS", func(v bool) { cfg.AutoAcceptSafeEdits = v }); err != nil {
		return meta, err
	} else if os.Getenv("GOCLI_POOR_AUTO_ACCEPT_SAFE_EDITS") != "" {
		meta.fields["auto_accept_safe_edits"] = true
	}
	for _, action := range DefaultActions {
		name := "GOCLI_POOR_KEYBINDINGS_" + strings.ToUpper(strings.ReplaceAll(action, ".", "_"))
		if stringEnv(name, func(v string) { cfg.Keybindings[action] = v }) {
			meta.keybindings[action] = true
		}
	}
	return meta, nil
}

func stringEnv(name string, set func(string)) bool {
	if v, ok := os.LookupEnv(name); ok {
		set(v)
		return true
	}
	return false
}

func intEnv(name string, set func(int)) error {
	if v, ok := os.LookupEnv(name); ok {
		n, err := strconv.Atoi(v)
		if err != nil {
			return fmt.Errorf("%s: expected integer: %w", name, err)
		}
		set(n)
	}
	return nil
}

func boolEnv(name string, set func(bool)) error {
	if v, ok := os.LookupEnv(name); ok {
		b, err := strconv.ParseBool(v)
		if err != nil {
			return fmt.Errorf("%s: expected bool: %w", name, err)
		}
		set(b)
	}
	return nil
}

func validateConfig(cfg *Config, meta fileMeta, env envMeta) error {
	switch cfg.LogLevel {
	case "debug", "info", "warn", "error":
	default:
		return withLine(meta, env, "log_level", fmt.Errorf("log_level: expected debug, info, warn, or error; got %q", cfg.LogLevel))
	}
	if cfg.ContextBudgetTokens <= 0 {
		return withLine(meta, env, "context_budget_tokens", fmt.Errorf("context_budget_tokens: expected positive integer; got %d", cfg.ContextBudgetTokens))
	}
	if cfg.MaxResponseTokens <= 0 {
		return withLine(meta, env, "max_response_tokens", fmt.Errorf("max_response_tokens: expected positive integer; got %d", cfg.MaxResponseTokens))
	}
	for _, action := range DefaultActions {
		if strings.TrimSpace(cfg.Keybindings[action]) == "" {
			return fmt.Errorf("keybindings.%s: missing binding", action)
		}
	}
	for action, binding := range cfg.Keybindings {
		if !knownAction(action) {
			return keybindLine(meta, env, action, fmt.Errorf("keybindings.%s: unknown action", action))
		}
		if _, err := parseBinding(binding); err != nil {
			return keybindLine(meta, env, action, fmt.Errorf("keybindings.%s: %w", action, err))
		}
	}
	return nil
}

func knownAction(action string) bool {
	for _, a := range DefaultActions {
		if action == a {
			return true
		}
	}
	return false
}

func withLine(meta fileMeta, env envMeta, field string, err error) error {
	if meta.path != "" && !env.fields[field] {
		if line := meta.fieldLines[field]; line != 0 {
			return fmt.Errorf("%s:%d: %w", meta.path, line, err)
		}
	}
	return err
}

func keybindLine(meta fileMeta, env envMeta, action string, err error) error {
	if meta.path != "" && meta.keybindSource[action] && !env.keybindings[action] {
		return fmt.Errorf("%s:%d: %w", meta.path, meta.keybindLines[action], err)
	}
	return err
}
