package tui

import "github.com/gongahkia/gocli-poor/internal/tui/emptystate"

type EmptyState = emptystate.EmptyState

const (
	EmptyFreshLaunch        = emptystate.FreshLaunch
	EmptyConnecting         = emptystate.Connecting
	EmptyDisconnected       = emptystate.Disconnected
	EmptyAPIKeyNeeded       = emptystate.APIKeyNeeded
	EmptyWaitingResponse    = emptystate.WaitingResponse
	EmptyStreaming          = emptystate.Streaming
	EmptyCancelled          = emptystate.Cancelled
	EmptyPendingEditsNone   = emptystate.PendingEditsNone
	EmptySessionsNone       = emptystate.SessionsNone
	EmptyUsersJustYou       = emptystate.UsersJustYou
	EmptySessionsLoading    = emptystate.SessionsLoading
	EmptyProvidersLoading   = emptystate.ProvidersLoading
	EmptyProvidersNone      = emptystate.ProvidersNone
	EmptyCostLoading        = emptystate.CostLoading
	EmptyFileCatalogLoading = emptystate.FileCatalogLoading
	EmptyMentionNoMatches   = emptystate.MentionNoMatches
	EmptyPreviewLoading     = emptystate.PreviewLoading
	EmptyPreviewEmpty       = emptystate.PreviewEmpty
)

func EmptyStateFor(key string, data ...any) EmptyState {
	return emptystate.EmptyStateFor(key, data...)
}
