package emptystate

import (
	"fmt"
	"strings"

	"github.com/gongahkia/gocli-poor/internal/theme"
)

const (
	FreshLaunch        = "fresh_launch"
	Connecting         = "connecting"
	Disconnected       = "disconnected"
	APIKeyNeeded       = "api_key_needed"
	WaitingResponse    = "waiting_response"
	Streaming          = "streaming"
	Cancelled          = "cancelled"
	PendingEditsNone   = "pending_edits_none"
	SessionsNone       = "sessions_none"
	UsersJustYou       = "users_just_you"
	SessionsLoading    = "sessions_loading"
	ProvidersLoading   = "providers_loading"
	ProvidersNone      = "providers_none"
	CostLoading        = "cost_loading"
	FileCatalogLoading = "file_catalog_loading"
	MentionNoMatches   = "mention_no_matches"
	PreviewLoading     = "preview_loading"
	PreviewEmpty       = "preview_empty"
)

type EmptyState struct {
	Key  string
	Text string
}

func EmptyStateFor(key string, data ...any) EmptyState {
	switch key {
	case FreshLaunch:
		return state(key, "ready.")
	case Connecting:
		return state(key, "gocli-poor · connecting")
	case Disconnected:
		return state(key, "gocli-poor · disconnected - press ctrl+r to retry")
	case APIKeyNeeded:
		return state(key, fmt.Sprintf("gocli-poor · %s needs an API key · press / for commands", provider(data...)))
	case WaitingResponse:
		return state(key, "poor-cli ›")
	case Streaming:
		return state(key, "")
	case Cancelled:
		return state(key, "- cancelled")
	case PendingEditsNone:
		return state(key, "pending edits · none")
	case SessionsNone:
		return state(key, "sessions · none yet")
	case UsersJustYou:
		return state(key, "users · just you")
	case SessionsLoading:
		return state(key, "sessions · loading")
	case ProvidersLoading:
		return state(key, "providers · loading")
	case ProvidersNone:
		return state(key, "providers · none")
	case CostLoading:
		return state(key, "cost · loading")
	case FileCatalogLoading:
		return state(key, "files · loading")
	case MentionNoMatches:
		return state(key, "files · no matches")
	case PreviewLoading:
		return state(key, "preview · loading")
	case PreviewEmpty:
		return state(key, "preview · empty")
	default:
		return state(key, "ready.")
	}
}

func (s EmptyState) Render(t *theme.Theme) string {
	text := oneLine(s.Text)
	if t == nil {
		tm := theme.DarkWithCapability(theme.CapabilityMonochrome)
		t = &tm
	}
	return t.Muted.Render(text)
}

func state(key, text string) EmptyState {
	return EmptyState{Key: key, Text: oneLine(text)}
}

func provider(data ...any) string {
	if len(data) == 0 {
		return "anthropic"
	}
	if value := strings.TrimSpace(fmt.Sprint(data[0])); value != "" {
		return value
	}
	return "anthropic"
}

func oneLine(text string) string {
	text = strings.ReplaceAll(text, "\r", " ")
	text = strings.ReplaceAll(text, "\n", " ")
	return strings.Join(strings.Fields(text), " ")
}
