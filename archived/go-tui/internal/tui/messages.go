package tui

import "time"

type ResizeMsg struct {
	Width  int
	Height int
}

type SwitchFocusMsg struct {
	Target FocusTarget
}

type OpenModalMsg struct {
	Kind    ModalKind
	Payload any
}

type CloseModalMsg struct{}

type ToastMsg struct {
	Kind ToastKind
	Text string
	TTL  time.Duration
}

type FocusTarget int

const (
	FocusIntro FocusTarget = iota
	FocusInput
	FocusChat
	FocusUsers
	FocusModal
)

type ModalKind int

const (
	ModalPalette ModalKind = iota
	ModalMention
	ModalCost
	ModalProviderPicker
	ModalSessionPicker
	ModalHelp
	ModalDiffReview
	ModalWatchPanel
	ModalRolePicker
	ModalAPIKeyPrompt
	ModalPermissionPrompt
)

type ToastKind int

const (
	ToastInfo ToastKind = iota
	ToastSuccess
	ToastWarning
	ToastError
)

type IntroDoneMsg struct{}

type InitializeOKMsg struct{}

type InitializeNeedsAPIKeyMsg struct {
	Provider string
	Message  string
}
