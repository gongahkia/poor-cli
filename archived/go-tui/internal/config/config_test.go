package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadPrecedenceXDGOverDefault(t *testing.T) {
	home := testHome(t)
	xdg := filepath.Join(home, "xdg")
	writeConfig(t, filepath.Join(home, ".config", "gocli-poor", "config.yaml"), "default_provider: default\n")
	writeConfig(t, filepath.Join(xdg, "gocli-poor", "config.yaml"), "default_provider: xdg\n")
	setenv(t, "XDG_CONFIG_HOME", xdg)
	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.DefaultProvider != "xdg" {
		t.Fatalf("DefaultProvider=%q", cfg.DefaultProvider)
	}
}

func TestLoadEnvOverride(t *testing.T) {
	home := testHome(t)
	writeConfig(t, filepath.Join(home, ".gocli-poor.yaml"), "default_provider: anthropic\nkeybindings:\n  palette: ctrl+p\n")
	setenv(t, "GOCLI_POOR_DEFAULT_PROVIDER", "openai")
	setenv(t, "GOCLI_POOR_KEYBINDINGS_PALETTE", "/")
	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.DefaultProvider != "openai" {
		t.Fatalf("DefaultProvider=%q", cfg.DefaultProvider)
	}
	if cfg.Keybindings[ActionPalette] != "/" {
		t.Fatalf("palette=%q", cfg.Keybindings[ActionPalette])
	}
}

func TestLoadPartialConfigMergesDefaults(t *testing.T) {
	home := testHome(t)
	writeConfig(t, filepath.Join(home, ".gocli-poor.yaml"), "default_provider: openai\nkeybindings:\n  palette: ctrl+p\ntheme:\n  name: custom\n  accent: focus\n")
	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.DefaultProvider != "openai" || cfg.DefaultModel != "claude-4-6-sonnet" {
		t.Fatalf("provider/model=%q/%q", cfg.DefaultProvider, cfg.DefaultModel)
	}
	if cfg.Keybindings[ActionPalette] != "ctrl+p" || cfg.Keybindings[ActionSubmit] != "ctrl+enter" {
		t.Fatalf("bad keybindings: %#v", cfg.Keybindings)
	}
	if cfg.Theme.Name != "custom" || cfg.Theme.Inline["accent"] != "focus" {
		t.Fatalf("bad theme: %#v", cfg.Theme)
	}
}

func TestDefaultAutoAcceptSafeEditsOn(t *testing.T) {
	if !DefaultConfig().AutoAcceptSafeEdits {
		t.Fatalf("AutoAcceptSafeEdits default off")
	}
}

func TestLoadRejectsUnknownKeybinding(t *testing.T) {
	home := testHome(t)
	path := filepath.Join(home, ".gocli-poor.yaml")
	writeConfig(t, path, "keybindings:\n  submit: ctrl+wat\n")
	_, err := Load()
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), path+":2") || !strings.Contains(err.Error(), "unknown key") {
		t.Fatalf("bad error: %v", err)
	}
}

func TestLoadEnvValidationDoesNotUseFileLine(t *testing.T) {
	home := testHome(t)
	path := filepath.Join(home, ".gocli-poor.yaml")
	writeConfig(t, path, "keybindings:\n  submit: ctrl+enter\n")
	setenv(t, "GOCLI_POOR_KEYBINDINGS_SUBMIT", "ctrl+wat")
	_, err := Load()
	if err == nil {
		t.Fatal("expected error")
	}
	if strings.Contains(err.Error(), path+":2") || !strings.Contains(err.Error(), "unknown key") {
		t.Fatalf("bad error: %v", err)
	}
}

func TestLoadRejectsMalformedYAML(t *testing.T) {
	home := testHome(t)
	path := filepath.Join(home, ".gocli-poor.yaml")
	writeConfig(t, path, "keybindings: [\n")
	_, err := Load()
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), path) {
		t.Fatalf("bad error: %v", err)
	}
}

func TestKeymapDispatchAndChords(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Keybindings[ActionPalette] = "ctrl+x p"
	km, err := NewKeymap(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if action, ok := km.ActionForKey("enter"); ok || action != "" {
		t.Fatalf("enter matched %q", action)
	}
	if action, ok := km.ActionForKey("ctrl+enter"); !ok || action != ActionSubmit {
		t.Fatalf("ctrl+enter matched %q %v", action, ok)
	}
	if action, ok := km.ActionForKey("ctrl+x"); ok || action != "" {
		t.Fatalf("prefix matched %q", action)
	}
	if action, ok := km.ActionForKey("p"); !ok || action != ActionPalette {
		t.Fatalf("chord matched %q %v", action, ok)
	}
	if action, ok := km.ActionForKey("esc"); !ok || action != ActionCancel {
		t.Fatalf("esc matched %q %v", action, ok)
	}
}

func testHome(t *testing.T) string {
	t.Helper()
	cleanEnv(t)
	home := t.TempDir()
	setenv(t, "HOME", home)
	return home
}

func writeConfig(t *testing.T, path, body string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

func cleanEnv(t *testing.T) {
	t.Helper()
	keys := []string{"HOME", "XDG_CONFIG_HOME", "POOR_CLI_SERVER_PATH"}
	for _, env := range os.Environ() {
		name, _, _ := strings.Cut(env, "=")
		if strings.HasPrefix(name, "GOCLI_POOR_") {
			keys = append(keys, name)
		}
	}
	seen := map[string]bool{}
	for _, key := range keys {
		if seen[key] {
			continue
		}
		seen[key] = true
		old, ok := os.LookupEnv(key)
		if err := os.Unsetenv(key); err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() {
			if ok {
				_ = os.Setenv(key, old)
			} else {
				_ = os.Unsetenv(key)
			}
		})
	}
}

func setenv(t *testing.T, key, value string) {
	t.Helper()
	old, ok := os.LookupEnv(key)
	if err := os.Setenv(key, value); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if ok {
			_ = os.Setenv(key, old)
		} else {
			_ = os.Unsetenv(key)
		}
	})
}
