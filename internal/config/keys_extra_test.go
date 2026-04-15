package config

import "testing"

type stringKey string

func (s stringKey) String() string { return string(s) }

func TestKeymapAliasesResetAndBindings(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Keybindings[ActionPalette] = "ctrl+x p"
	cfg.Keybindings[ActionMention] = "alt+return"
	cfg.Keybindings[ActionUsersPass] = "f13"
	km, err := NewKeymap(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if action, ok := km.ActionForKeyMsg(stringKey("ctrl+x")); ok || action != "" {
		t.Fatalf("prefix action=%q ok=%v", action, ok)
	}
	km.ResetChord()
	if action, ok := km.ActionForKey("p"); ok || action != "" {
		t.Fatalf("reset chord leaked action=%q ok=%v", action, ok)
	}
	if action, ok := km.ActionForKey("alt+return"); !ok || action != ActionMention {
		t.Fatalf("alt alias action=%q ok=%v", action, ok)
	}
	if len(km.Bindings()) != len(DefaultActions) {
		t.Fatalf("bindings len=%d", len(km.Bindings()))
	}
}

func TestKeymapFunctionCtrlAndInvalidKeys(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Keybindings[ActionQuit] = "f24"
	cfg.Keybindings[ActionRegenEdit] = "ctrl+?"
	km, err := NewKeymap(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if action, ok := km.ActionForKey("f24"); !ok || action != ActionQuit {
		t.Fatalf("f24 action=%q ok=%v", action, ok)
	}
	if action, ok := km.ActionForKey("ctrl+?"); !ok || action != ActionRegenEdit {
		t.Fatalf("ctrl+? action=%q ok=%v", action, ok)
	}
	if action, ok := km.ActionForKey("ctrl+shift+wat"); ok || action != "" {
		t.Fatalf("invalid action=%q ok=%v", action, ok)
	}
}
