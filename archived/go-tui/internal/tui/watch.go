package tui

import (
	"context"
	"errors"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/tui/flows"
)

type watchStatusLoadedMsg struct {
	Status map[string]any
	Err    error
}

func fetchWatchStatusCmd(rpc flows.RPCClient) tea.Cmd {
	return func() tea.Msg {
		if rpc == nil {
			return watchStatusLoadedMsg{Err: errors.New("watch rpc unavailable")}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		var result map[string]any
		err := rpc.Call(ctx, protocol.MethodWatchStatus, map[string]any{"limit": 20}, &result)
		return watchStatusLoadedMsg{Status: result, Err: err}
	}
}
