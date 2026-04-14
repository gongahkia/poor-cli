package config

const (
	ActionSubmit       = "submit"
	ActionCancel       = "cancel"
	ActionPalette      = "palette"
	ActionMention      = "mention"
	ActionFocusChat    = "focus.chat"
	ActionFocusInput   = "focus.input"
	ActionScrollUp     = "scroll.up"
	ActionScrollDown   = "scroll.down"
	ActionScrollTop    = "scroll.top"
	ActionScrollBottom = "scroll.bottom"
	ActionAcceptEdit   = "accept.edit"
	ActionRejectEdit   = "reject.edit"
	ActionRegenEdit    = "regen.edit"
	ActionQuit         = "quit"
)

var DefaultActions = []string{
	ActionSubmit,
	ActionCancel,
	ActionPalette,
	ActionMention,
	ActionFocusChat,
	ActionFocusInput,
	ActionScrollUp,
	ActionScrollDown,
	ActionScrollTop,
	ActionScrollBottom,
	ActionAcceptEdit,
	ActionRejectEdit,
	ActionRegenEdit,
	ActionQuit,
}

func DefaultConfig() *Config {
	return &Config{
		Theme:               Theme{Name: "dark"},
		ServerPath:          "",
		DefaultProvider:     "anthropic",
		DefaultModel:        "claude-4-6-sonnet",
		ContextBudgetTokens: 180000,
		MaxResponseTokens:   8192,
		AutoAcceptSafeEdits: false,
		HistoryFile:         "~/.local/share/gocli-poor/history",
		LogLevel:            "info",
		Keybindings:         DefaultKeybindings(),
	}
}

func DefaultKeybindings() map[string]string {
	return map[string]string{
		ActionSubmit:       "ctrl+enter",
		ActionCancel:       "ctrl+c,esc",
		ActionPalette:      "/",
		ActionMention:      "@",
		ActionFocusChat:    "ctrl+j",
		ActionFocusInput:   "ctrl+i",
		ActionScrollUp:     "pgup",
		ActionScrollDown:   "pgdn",
		ActionScrollTop:    "home",
		ActionScrollBottom: "end",
		ActionAcceptEdit:   "ctrl+y",
		ActionRejectEdit:   "ctrl+n",
		ActionRegenEdit:    "ctrl+r",
		ActionQuit:         "ctrl+q",
	}
}
