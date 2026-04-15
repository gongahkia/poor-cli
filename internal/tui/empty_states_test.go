package tui

import (
	"strings"
	"testing"
)

func TestEmptyStateFor(t *testing.T) {
	tests := []struct {
		key  string
		data []any
		want string
	}{
		{key: EmptyFreshLaunch, want: "ready."},
		{key: EmptyConnecting, want: "gocli-poor · connecting…"},
		{key: EmptyDisconnected, want: "gocli-poor · disconnected - press ctrl+r to retry"},
		{key: EmptyAPIKeyNeeded, data: []any{"anthropic"}, want: "gocli-poor · anthropic needs an API key · press / for commands"},
		{key: EmptyWaitingResponse, want: "poor-cli › ·"},
		{key: EmptyStreaming, want: ""},
		{key: EmptyCancelled, want: "- cancelled"},
		{key: EmptyPendingEditsNone, want: "pending edits · none"},
		{key: EmptySessionsNone, want: "sessions · none yet"},
		{key: EmptyUsersJustYou, want: "users · just you"},
	}
	for _, tt := range tests {
		got := EmptyStateFor(tt.key, tt.data...)
		if got.Key != tt.key || got.Text != tt.want {
			t.Fatalf("%s: got %#v want %q", tt.key, got, tt.want)
		}
		if strings.ContainsAny(got.Text, "\r\n") {
			t.Fatalf("%s: multiline %q", tt.key, got.Text)
		}
	}
}
