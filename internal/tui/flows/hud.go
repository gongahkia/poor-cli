package flows

import (
	"context"
	"sync"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
)

const (
	hudCostInterval       = 100 * time.Millisecond
	hudContextIdleEvery   = 5 * time.Second
	hudContextStreamEvery = time.Second
	hudContextWarnPct     = 80.0
	hudToastTTL           = 3 * time.Second
)

type HudFlow struct {
	rpc     RPCClient
	state   StateDispatcher
	store   *state.Store
	context func() context.Context
	now     func() time.Time

	mu            sync.Mutex
	pendingCost   *protocol.CostSnapshot
	lastCostPaint time.Time
	lastCtxPct    float64
	unsubs        []func()
	stop          chan struct{}
	stopOnce      sync.Once
	wg            sync.WaitGroup
}

type hudTickMsg struct{}

func NewHudFlow(d Deps) *HudFlow {
	f := &HudFlow{
		rpc:     d.RPC,
		state:   d.State,
		store:   d.Store,
		context: d.Context,
		now:     d.Now,
		stop:    make(chan struct{}),
	}
	if f.state == nil && d.Store != nil {
		f.state = d.Store
	}
	if f.context == nil {
		f.context = context.Background
	}
	if f.now == nil {
		f.now = time.Now
	}
	return f
}

func (h *HudFlow) Name() string { return "hud" }

func (h *HudFlow) StartFlow(ctx context.Context, d Deps) error {
	h.applyDeps(d)
	sub, _ := h.rpc.(NotificationSubscriber)
	if sub != nil {
		h.unsubs = append(h.unsubs,
			sub.Subscribe(protocol.MethodCostUpdate, h.onCostUpdate),
			sub.Subscribe(protocol.MethodContextPressure, h.onContextPressure),
			sub.Subscribe(protocol.MethodContextStatus, h.onContextPressure),
		)
		h.wg.Add(1)
		go h.costLoop()
	}
	if h.rpc != nil {
		h.wg.Add(1)
		go h.contextLoop(ctx)
	}
	return nil
}

func (h *HudFlow) Stop() error {
	h.stopOnce.Do(func() { close(h.stop) })
	for _, unsub := range h.unsubs {
		unsub()
	}
	h.wg.Wait()
	return nil
}

func (h *HudFlow) Update(msg tea.Msg) tea.Cmd {
	if _, ok := msg.(hudTickMsg); !ok {
		return nil
	}
	h.flushCost()
	return tea.Tick(hudCostInterval, func(time.Time) tea.Msg { return hudTickMsg{} })
}

func (h *HudFlow) onCostUpdate(params any) {
	var update protocol.CostUpdate
	if !decodeNotification(params, &update) {
		return
	}
	snapshot := costSnapshotFromUpdate(update)
	h.mu.Lock()
	h.pendingCost = &snapshot
	h.mu.Unlock()
}

func (h *HudFlow) onContextPressure(params any) {
	if pressure, ok := decodeContextPressure(params); ok {
		h.updateContextPressure(pressure)
	}
}

func (h *HudFlow) flushCost() bool {
	h.mu.Lock()
	pending := h.pendingCost
	if pending == nil {
		h.mu.Unlock()
		return false
	}
	snapshot := *pending
	h.pendingCost = nil
	updatedAt := h.timeNow()
	h.lastCostPaint = updatedAt
	h.mu.Unlock()
	h.dispatch(state.ActionUpdateCost{Snapshot: snapshot, UpdatedAt: updatedAt})
	return true
}

func (h *HudFlow) pollContextPressure() {
	var pressure protocol.ContextPressure
	if err := callRPC(h.rpc, protocol.MethodGetContextPressure, nil, &pressure); err != nil {
		return
	}
	h.updateContextPressure(pressure)
}

func (h *HudFlow) updateContextPressure(pressure protocol.ContextPressure) {
	next := contextPressureState(pressure)
	pct := normalizeContextPct(next.Pct)
	h.mu.Lock()
	prev := h.lastCtxPct
	h.lastCtxPct = pct
	h.mu.Unlock()
	h.dispatch(state.ActionUpdateContextPressure{Pressure: next})
	if pct >= hudContextWarnPct && prev < hudContextWarnPct {
		h.dispatch(state.ActionToast{Kind: state.ToastWarning, Text: "context pressure above 80%", TTL: hudToastTTL})
	}
}

func (h *HudFlow) costLoop() {
	defer h.wg.Done()
	ticker := time.NewTicker(hudCostInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			h.flushCost()
		case <-h.stop:
			h.flushCost()
			return
		}
	}
}

func (h *HudFlow) contextLoop(ctx context.Context) {
	defer h.wg.Done()
	timer := time.NewTimer(h.contextInterval())
	defer timer.Stop()
	for {
		select {
		case <-timer.C:
			h.pollContextPressure()
			timer.Reset(h.contextInterval())
		case <-ctx.Done():
			return
		case <-h.stop:
			return
		}
	}
}

func (h *HudFlow) contextInterval() time.Duration {
	if h.store != nil && h.store.Snapshot().InFlight != nil {
		return hudContextStreamEvery
	}
	return hudContextIdleEvery
}

func (h *HudFlow) applyDeps(d Deps) {
	if h.rpc == nil {
		h.rpc = d.RPC
	}
	if h.state == nil {
		h.state = d.State
	}
	if h.state == nil && d.Store != nil {
		h.state = d.Store
	}
	if h.store == nil {
		h.store = d.Store
	}
	if h.context == nil {
		h.context = d.Context
	}
	if h.context == nil {
		h.context = context.Background
	}
	if h.now == nil {
		h.now = d.Now
	}
	if h.now == nil {
		h.now = time.Now
	}
	if h.stop == nil {
		h.stop = make(chan struct{})
	}
}

func (h *HudFlow) dispatch(action state.Action) {
	if h.state != nil {
		h.state.Dispatch(action)
	}
}

func (h *HudFlow) timeNow() time.Time {
	if h.now == nil {
		return time.Now()
	}
	return h.now()
}

func costSnapshotFromUpdate(update protocol.CostUpdate) protocol.CostSnapshot {
	inputTokens := update.InputTokens
	outputTokens := update.OutputTokens
	if update.CumulativeInputTokens != nil {
		inputTokens = *update.CumulativeInputTokens
	}
	if update.CumulativeOutputTokens != nil {
		outputTokens = *update.CumulativeOutputTokens
	}
	cacheRead := 0
	if update.CacheReadTokens != nil {
		cacheRead = *update.CacheReadTokens
	}
	if update.CacheReadInputTokens != nil {
		cacheRead = *update.CacheReadInputTokens
	}
	cacheWrite := 0
	if update.CacheWriteTokens != nil {
		cacheWrite = *update.CacheWriteTokens
	}
	if update.CacheCreationInputTokens != nil {
		cacheWrite = *update.CacheCreationInputTokens
	}
	return protocol.CostSnapshot{
		TotalCost:        update.EstimatedCost,
		InputTokens:      inputTokens,
		OutputTokens:     outputTokens,
		CacheReadTokens:  cacheRead,
		CacheWriteTokens: cacheWrite,
		Summary: protocol.CostSummary{
			InputTokens:                   inputTokens,
			OutputTokens:                  outputTokens,
			EstimatedCostUSD:              update.EstimatedCost,
			CacheReadTokens:               cacheRead,
			CacheCreationInputTokens:      cacheWrite,
			CacheCreationInputTokensCamel: cacheWrite,
			CacheReadInputTokens:          cacheRead,
			CacheReadInputTokensCamel:     cacheRead,
		},
	}
}

func decodeContextPressure(params any) (protocol.ContextPressure, bool) {
	var pressure protocol.ContextPressure
	if decodeNotification(params, &pressure) && !emptyContextPressure(pressure) {
		return pressure, true
	}
	var wrapped struct {
		Pressure        protocol.ContextPressure `json:"pressure"`
		ContextPressure protocol.ContextPressure `json:"contextPressure"`
	}
	if decodeNotification(params, &wrapped) {
		if !emptyContextPressure(wrapped.Pressure) {
			return wrapped.Pressure, true
		}
		if !emptyContextPressure(wrapped.ContextPressure) {
			return wrapped.ContextPressure, true
		}
	}
	return protocol.ContextPressure{}, false
}

func emptyContextPressure(p protocol.ContextPressure) bool {
	return p.UsedTokens == 0 && p.MaxTokens == 0 && p.PressurePct == 0 &&
		p.UsedTokensCamel == 0 && p.MaxTokensCamel == 0 && p.PressurePctCamel == 0 &&
		p.BudgetTokens == 0 && p.Percent == 0
}

func contextPressureState(p protocol.ContextPressure) state.ContextPressure {
	tokens := firstNonZero(p.UsedTokens, p.UsedTokensCamel)
	budget := firstNonZero(p.MaxTokens, p.MaxTokensCamel, p.BudgetTokens)
	pct := firstNonZeroFloat(p.PressurePct, p.PressurePctCamel, p.Percent)
	if pct == 0 && budget > 0 {
		pct = float64(tokens) / float64(budget) * 100
	}
	return state.ContextPressure{Tokens: tokens, Budget: budget, Pct: pct}
}

func normalizeContextPct(pct float64) float64 {
	if pct <= 1 {
		return pct * 100
	}
	return pct
}
