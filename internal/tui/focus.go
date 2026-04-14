package tui

import tea "github.com/charmbracelet/bubbletea"

type KeyOwner int

const (
	KeyOwnerNone KeyOwner = iota
	KeyOwnerInput
	KeyOwnerChat
	KeyOwnerModal
	KeyOwnerGlobal
)

type FocusRouter struct {
	Target FocusTarget
}

func NewFocusRouter() FocusRouter {
	return FocusRouter{Target: FocusInput}
}

func (r FocusRouter) WithTarget(target FocusTarget) FocusRouter {
	r.Target = target
	return r
}

func (r FocusRouter) Owns(msg tea.KeyMsg) KeyOwner {
	if r.Target == FocusModal {
		return KeyOwnerModal
	}
	switch msg.String() {
	case "ctrl+c", "ctrl+q", "ctrl+j", "ctrl+i":
		return KeyOwnerGlobal
	case "esc":
		return KeyOwnerGlobal
	}
	if r.Target == FocusChat {
		return chatKeyOwner(msg)
	}
	if r.Target == FocusInput || r.Target == FocusIntro {
		return inputKeyOwner(msg)
	}
	return KeyOwnerNone
}

func inputKeyOwner(msg tea.KeyMsg) KeyOwner {
	switch msg.String() {
	case "pgup", "pgdown", "home", "end":
		return KeyOwnerGlobal
	default:
		return KeyOwnerInput
	}
}

func chatKeyOwner(msg tea.KeyMsg) KeyOwner {
	switch msg.String() {
	case "pgup", "pgdown", "home", "end", "up", "down":
		return KeyOwnerChat
	default:
		return KeyOwnerGlobal
	}
}
