package config

import (
	"fmt"
	"strings"
	"unicode"

	"github.com/charmbracelet/bubbles/key"
)

type Keymap struct {
	Submit       key.Binding
	Cancel       key.Binding
	Palette      key.Binding
	Mention      key.Binding
	FocusChat    key.Binding
	FocusInput   key.Binding
	FocusUsers   key.Binding
	ScrollUp     key.Binding
	ScrollDown   key.Binding
	ScrollTop    key.Binding
	ScrollBottom key.Binding
	UsersApprove key.Binding
	UsersDeny    key.Binding
	UsersKick    key.Binding
	UsersRole    key.Binding
	UsersPass    key.Binding
	AcceptEdit   key.Binding
	RejectEdit   key.Binding
	RegenEdit    key.Binding
	Quit         key.Binding
	actions      map[string]actionBinding
	pending      []string
}

type actionBinding struct {
	action    string
	sequences [][]string
	binding   key.Binding
}

func NewKeymap(c *Config) (*Keymap, error) {
	var k Keymap
	if err := k.FromConfig(c); err != nil {
		return nil, err
	}
	return &k, nil
}

func (k *Keymap) FromConfig(c *Config) error {
	raw := DefaultKeybindings()
	if c != nil {
		for action, binding := range c.Keybindings {
			raw[action] = binding
		}
	}
	k.actions = map[string]actionBinding{}
	k.pending = nil
	for action, binding := range raw {
		if !knownAction(action) {
			return fmt.Errorf("keybindings.%s: unknown action", action)
		}
		sequences, err := parseBinding(binding)
		if err != nil {
			return fmt.Errorf("keybindings.%s: %w", action, err)
		}
		k.actions[action] = actionBinding{action: action, sequences: sequences, binding: bindingFor(sequences)}
	}
	for _, action := range DefaultActions {
		if _, ok := k.actions[action]; !ok {
			return fmt.Errorf("keybindings.%s: missing binding", action)
		}
	}
	k.Submit = k.actions[ActionSubmit].binding
	k.Cancel = k.actions[ActionCancel].binding
	k.Palette = k.actions[ActionPalette].binding
	k.Mention = k.actions[ActionMention].binding
	k.FocusChat = k.actions[ActionFocusChat].binding
	k.FocusInput = k.actions[ActionFocusInput].binding
	k.FocusUsers = k.actions[ActionFocusUsers].binding
	k.ScrollUp = k.actions[ActionScrollUp].binding
	k.ScrollDown = k.actions[ActionScrollDown].binding
	k.ScrollTop = k.actions[ActionScrollTop].binding
	k.ScrollBottom = k.actions[ActionScrollBottom].binding
	k.UsersApprove = k.actions[ActionUsersApprove].binding
	k.UsersDeny = k.actions[ActionUsersDeny].binding
	k.UsersKick = k.actions[ActionUsersKick].binding
	k.UsersRole = k.actions[ActionUsersRole].binding
	k.UsersPass = k.actions[ActionUsersPass].binding
	k.AcceptEdit = k.actions[ActionAcceptEdit].binding
	k.RejectEdit = k.actions[ActionRejectEdit].binding
	k.RegenEdit = k.actions[ActionRegenEdit].binding
	k.Quit = k.actions[ActionQuit].binding
	return nil
}

func (k *Keymap) ActionForKeyMsg(msg interface{ String() string }) (string, bool) {
	return k.ActionForKey(msg.String())
}

func (k *Keymap) ActionForKey(keyName string) (string, bool) {
	keyName, err := canonicalKey(keyName)
	if err != nil {
		k.pending = nil
		return "", false
	}
	if len(k.pending) > 0 {
		candidate := append(append([]string(nil), k.pending...), keyName)
		if action, ok := k.matchExact(candidate); ok {
			k.pending = nil
			return action, true
		}
		if k.hasPrefix(candidate) {
			k.pending = candidate
			return "", false
		}
		k.pending = nil
	}
	seq := []string{keyName}
	if action, ok := k.matchExact(seq); ok {
		return action, true
	}
	if k.hasPrefix(seq) {
		k.pending = seq
		return "", false
	}
	return "", false
}

func (k *Keymap) ResetChord() {
	k.pending = nil
}

func (k *Keymap) Bindings() map[string]key.Binding {
	out := make(map[string]key.Binding, len(k.actions))
	for action, binding := range k.actions {
		out[action] = binding.binding
	}
	return out
}

func (k *Keymap) matchExact(seq []string) (string, bool) {
	for action, binding := range k.actions {
		for _, candidate := range binding.sequences {
			if sameSeq(seq, candidate) {
				return action, true
			}
		}
	}
	return "", false
}

func (k *Keymap) hasPrefix(seq []string) bool {
	for _, binding := range k.actions {
		for _, candidate := range binding.sequences {
			if len(candidate) > len(seq) && sameSeq(seq, candidate[:len(seq)]) {
				return true
			}
		}
	}
	return false
}

func sameSeq(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func bindingFor(sequences [][]string) key.Binding {
	keys := make([]string, 0, len(sequences))
	for _, seq := range sequences {
		keys = append(keys, strings.Join(seq, " "))
	}
	return key.NewBinding(key.WithKeys(keys...))
}

func parseBinding(raw string) ([][]string, error) {
	alts := strings.Split(raw, ",")
	sequences := make([][]string, 0, len(alts))
	for _, alt := range alts {
		alt = strings.TrimSpace(alt)
		if alt == "" {
			return nil, fmt.Errorf("empty keybinding")
		}
		parts := strings.Fields(alt)
		seq := make([]string, 0, len(parts))
		for _, part := range parts {
			k, err := canonicalKey(part)
			if err != nil {
				return nil, err
			}
			seq = append(seq, k)
		}
		sequences = append(sequences, seq)
	}
	return sequences, nil
}

func canonicalKey(s string) (string, error) {
	s = strings.TrimSpace(strings.ToLower(s))
	if s == "" {
		return "", fmt.Errorf("empty key")
	}
	if strings.HasPrefix(s, "alt+") {
		base, err := canonicalKey(strings.TrimPrefix(s, "alt+"))
		if err != nil {
			return "", err
		}
		return "alt+" + base, nil
	}
	switch s {
	case "escape":
		return "esc", nil
	case "return":
		return "enter", nil
	case "pgdn", "pagedown":
		return "pgdown", nil
	case "pageup":
		return "pgup", nil
	case "ctrl+i":
		return "tab", nil
	}
	if isKnownKey(s) {
		return s, nil
	}
	return "", fmt.Errorf("unknown key %q", s)
}

func isKnownKey(s string) bool {
	if len([]rune(s)) == 1 {
		r := []rune(s)[0]
		return !unicode.IsControl(r)
	}
	if strings.HasPrefix(s, "ctrl+") {
		rest := strings.TrimPrefix(s, "ctrl+")
		if len(rest) == 1 && ((rest[0] >= 'a' && rest[0] <= 'z') || strings.ContainsRune("@\\]^_?", rune(rest[0]))) {
			return true
		}
	}
	if strings.HasPrefix(s, "f") {
		n := strings.TrimPrefix(s, "f")
		switch n {
		case "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24":
			return true
		}
	}
	switch s {
	case "enter", "ctrl+enter", "esc", "tab", "shift+tab", "backspace", "delete", "insert",
		"home", "end", "pgup", "pgdown", "up", "down", "left", "right",
		"ctrl+home", "ctrl+end", "ctrl+pgup", "ctrl+pgdown", "ctrl+up", "ctrl+down", "ctrl+left", "ctrl+right",
		"shift+home", "shift+end", "shift+up", "shift+down", "shift+left", "shift+right",
		"ctrl+shift+home", "ctrl+shift+end", "ctrl+shift+up", "ctrl+shift+down", "ctrl+shift+left", "ctrl+shift+right":
		return true
	default:
		return false
	}
}
