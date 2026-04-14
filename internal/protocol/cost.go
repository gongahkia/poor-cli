package protocol

type CostSnapshot struct {
	Session                       CostSession      `json:"session,omitempty"`
	Summary                       CostSummary      `json:"summary,omitempty"`
	SessionCost                   float64          `json:"sessionCost,omitempty"`
	TotalCost                     float64          `json:"totalCost,omitempty"`
	InputTokens                   int              `json:"inputTokens,omitempty"`
	OutputTokens                  int              `json:"outputTokens,omitempty"`
	CacheReadTokens               int              `json:"cacheReadTokens,omitempty"`
	PerProvider                   map[string]any   `json:"perProvider,omitempty"`
	PerTurn                       []map[string]any `json:"per_turn,omitempty"`
	PerTurnCamel                  []map[string]any `json:"perTurn,omitempty"`
	LastTurn                      map[string]any   `json:"last_turn,omitempty"`
	LastTurnCamel                 map[string]any   `json:"lastTurn,omitempty"`
	TopTools                      []map[string]any `json:"top_tools,omitempty"`
	TopToolsCamel                 []map[string]any `json:"topTools,omitempty"`
	ProjectedMonthlyUSD           float64          `json:"projected_monthly_usd,omitempty"`
	ProjectedMonthlyUSDCamel      float64          `json:"projectedMonthlyUSD,omitempty"`
	ProjectedMonthlyLastWeekUSD   float64          `json:"projected_monthly_last_week_usd,omitempty"`
	ProjectedMonthlyLastWeekCamel float64          `json:"projectedMonthlyLastWeekUSD,omitempty"`
	Daily                         map[string]any   `json:"daily,omitempty"`
	Cache                         map[string]any   `json:"cache,omitempty"`
}

type CostSession struct {
	TotalUSD     float64        `json:"total_usd"`
	TotalTokens  map[string]int `json:"total_tokens,omitempty"`
	Turns        int            `json:"turns,omitempty"`
	CacheHitRate float64        `json:"cache_hit_rate,omitempty"`
}

type CostSummary struct {
	InputTokens                    int            `json:"input_tokens,omitempty"`
	OutputTokens                   int            `json:"output_tokens,omitempty"`
	TotalTokens                    int            `json:"total_tokens,omitempty"`
	EstimatedCostUSD               float64        `json:"estimated_cost_usd,omitempty"`
	ToolFiltering                  map[string]any `json:"tool_filtering,omitempty"`
	ToolFilteringTokensSaved       int            `json:"tool_filtering_tokens_saved,omitempty"`
	SafePretokenization            map[string]any `json:"safe_pretokenization,omitempty"`
	SafePretokenizationTokensSaved int            `json:"safe_pretokenization_tokens_saved,omitempty"`
	BlockCache                     map[string]any `json:"block_cache,omitempty"`
	CacheCreationInputTokens       int            `json:"cache_creation_input_tokens,omitempty"`
	CacheReadInputTokens           int            `json:"cache_read_input_tokens,omitempty"`
	CacheHitCount                  int            `json:"cache_hit_count,omitempty"`
	CacheMissCount                 int            `json:"cache_miss_count,omitempty"`
	CacheHitRatePct                float64        `json:"cache_hit_rate_pct,omitempty"`
	EstimatedCacheSavingsUSD       float64        `json:"estimated_cache_savings_usd,omitempty"`
	RequestCount                   int            `json:"request_count,omitempty"`
	InputTokensCamel               int            `json:"inputTokens,omitempty"`
	OutputTokensCamel              int            `json:"outputTokens,omitempty"`
	TotalTokensCamel               int            `json:"totalTokens,omitempty"`
	EstimatedCost                  float64        `json:"estimatedCost,omitempty"`
	ToolFilteringCamel             map[string]any `json:"toolFiltering,omitempty"`
	ToolFilteringTokensSavedCamel  int            `json:"toolFilteringTokensSaved,omitempty"`
	SafePretokenizationCamel       map[string]any `json:"safePretokenization,omitempty"`
	SafePretokenizationTokensCamel int            `json:"safePretokenizationTokensSaved,omitempty"`
	BlockCacheCamel                map[string]any `json:"blockCache,omitempty"`
	CacheCreationInputTokensCamel  int            `json:"cacheCreationInputTokens,omitempty"`
	CacheReadInputTokensCamel      int            `json:"cacheReadInputTokens,omitempty"`
	CacheHitCountCamel             int            `json:"cacheHitCount,omitempty"`
	CacheMissCountCamel            int            `json:"cacheMissCount,omitempty"`
	CacheHitRatePctCamel           float64        `json:"cacheHitRatePct,omitempty"`
	EstimatedCacheSavingsUSDCamel  float64        `json:"estimatedCacheSavingsUSD,omitempty"`
	RequestCountCamel              int            `json:"requestCount,omitempty"`
	SessionCost                    float64        `json:"sessionCost,omitempty"`
	TotalCost                      float64        `json:"totalCost,omitempty"`
	CacheReadTokens                int            `json:"cacheReadTokens,omitempty"`
	PerProvider                    map[string]any `json:"perProvider,omitempty"`
}

type ContextPressure struct {
	UsedTokens       int     `json:"used_tokens,omitempty"`
	MaxTokens        int     `json:"max_tokens,omitempty"`
	PressurePct      float64 `json:"pressure_pct,omitempty"`
	StrategyHint     string  `json:"strategy_hint,omitempty"`
	UsedTokensCamel  int     `json:"usedTokens,omitempty"`
	MaxTokensCamel   int     `json:"maxTokens,omitempty"`
	PressurePctCamel float64 `json:"pressurePct,omitempty"`
	BudgetTokens     int     `json:"budgetTokens,omitempty"`
	Percent          float64 `json:"percent,omitempty"`
	Warning          string  `json:"warning,omitempty"`
}

type ContextBreakdown struct {
	SystemTokens     int            `json:"system_tokens,omitempty"`
	HistoryTokens    int            `json:"history_tokens,omitempty"`
	ToolResultTokens int            `json:"tool_result_tokens,omitempty"`
	TotalTokens      int            `json:"total_tokens,omitempty"`
	MaxContextTokens int            `json:"max_context_tokens,omitempty"`
	PressurePct      float64        `json:"pressure_pct,omitempty"`
	TurnCount        int            `json:"turn_count,omitempty"`
	ByCategory       map[string]int `json:"byCategory,omitempty"`
	Total            int            `json:"total,omitempty"`
}

type SavingsSnapshot struct {
	BySource              []SavingsSource    `json:"by_source,omitempty"`
	AllSources            []SavingsSource    `json:"all_sources,omitempty"`
	SourceOrder           []string           `json:"source_order,omitempty"`
	TokensSaved           int                `json:"tokens_saved,omitempty"`
	USDSaved              float64            `json:"usd_saved,omitempty"`
	SessionDelta          map[string]any     `json:"session_delta,omitempty"`
	Methodology           map[string]string  `json:"methodology,omitempty"`
	History               map[string]any     `json:"history,omitempty"`
	TopContributorsByWeek []map[string]any   `json:"top_contributors_by_week,omitempty"`
	TotalSavedUSD         float64            `json:"totalSavedUsd,omitempty"`
	ByStrategy            map[string]float64 `json:"byStrategy,omitempty"`
	LastUpdatedAt         int64              `json:"lastUpdatedAt,omitempty"`
}

type SavingsSource struct {
	Source      string  `json:"source"`
	TokensSaved int     `json:"tokens_saved"`
	USDSaved    float64 `json:"usd_saved"`
	Methodology string  `json:"methodology,omitempty"`
}
