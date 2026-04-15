package protocol

import (
	"encoding/json"
	"reflect"
	"testing"
)

func TestProtocolRoundTrips(t *testing.T) {
	tests := []struct {
		name string
		dst  any
		json string
	}{
		{"InitializeParams", &InitializeParams{}, `{"provider":"openai","model":"gpt-5.4","apiKey":"sk-test","streaming":true,"permissionMode":"default","sandboxPreset":"workspace-write","clientCapabilities":{"reviewFlows":{"permissionRequests":true}}}`},
		{"InitializeResult", &InitializeResult{}, `{"capabilities":{"completionProvider":true,"inlineCompletionProvider":true,"completionStreamingProvider":true,"chatProvider":true,"chatStreamingProvider":true,"fileOperations":true,"permissionMode":"default","sandboxPreset":"workspace-write","serverLogPath":"/tmp/poor.log","providerInfo":{"name":"openai","model":"gpt-5.4","routingMode":"manual","capabilities":{"streaming":true},"supported_clients":["nvim"]},"guardedFlow":{"permissionRequests":true,"planReview":true},"security":{"trustedWorkspaceBoundary":true,"trustedRoots":["/repo"]},"repoIndex":{"files":10,"symbols":20,"status":"ready"}}}`},
		{"Capabilities", &Capabilities{}, `{"completionProvider":true,"inlineCompletionProvider":true,"completionStreamingProvider":true,"chatProvider":true,"chatStreamingProvider":true,"fileOperations":true,"permissionMode":"default","sandboxPreset":"workspace-write","serverLogPath":"/tmp/poor.log","providerInfo":{"name":"openai","model":"gpt-5.4"},"guardedFlow":{"permissionRequests":true,"planReview":true},"security":{"trustedWorkspaceBoundary":true,"trustedRoots":["/repo"]},"repoIndex":{"files":1,"symbols":2,"status":"ready"},"needsApiKey":true,"message":"missing key"}`},
		{"GuardedFlow", &GuardedFlow{}, `{"permissionRequests":true,"planReview":true}`},
		{"SecurityCaps", &SecurityCaps{}, `{"trustedWorkspaceBoundary":true,"trustedRoots":["/repo"]}`},
		{"RepoIndexStats", &RepoIndexStats{}, `{"files":1,"symbols":2,"status":"ready"}`},
		{"ChatParams", &ChatParams{}, `{"message":"hi","contextFiles":["main.go"],"pinnedContextFiles":["README.md"],"contextBudgetTokens":2000,"requestId":"r1","sessionId":"s1"}`},
		{"ChatStreamingParams", &ChatStreamingParams{}, `{"message":"hi","contextFiles":["main.go"],"pinnedContextFiles":["README.md"],"contextBudgetTokens":2000,"maxResponseTokens":4000,"requestId":"r1","editTurnId":"turn1","sessionId":"s1"}`},
		{"ChatResult", &ChatResult{}, `{"content":"hello","role":"assistant"}`},
		{"StreamChunk", &StreamChunk{}, `{"requestId":"r1","chunk":"hello","done":false,"reason":"complete"}`},
		{"ThinkingChunk", &ThinkingChunk{}, `{"requestId":"r1","chunk":"thinking"}`},
		{"ToolEvent", &ToolEvent{}, `{"requestId":"r1","eventType":"tool_result","toolName":"read_file","toolArgs":{"path":"main.go"},"toolResult":"ok","callId":"c1","diff":"@@","paths":["main.go"],"checkpointId":"cp1","changed":true,"message":"done","outputFilter":{"mode":"summary"},"originalSize":100,"filteredSize":20,"iterationIndex":1,"iterationCap":25}`},
		{"CostUpdate", &CostUpdate{}, `{"requestId":"r1","inputTokens":10,"outputTokens":5,"estimatedCost":0.01,"modelName":"gpt-5.4","cacheReadTokens":2,"cacheWriteTokens":3,"cacheCreationInputTokens":3,"cacheReadInputTokens":2,"cumulativeInputTokens":12,"cumulativeOutputTokens":6,"systemTokens":1,"historyTokens":2,"toolResultTokens":3,"isEstimate":true,"confidencePercent":90,"confidenceCategory":"high"}`},
		{"Progress", &Progress{}, `{"requestId":"r1","phase":"repo_index","message":"indexing","iterationIndex":1,"iterationCap":25}`},
		{"PermissionReq", &PermissionReq{}, `{"requestId":"r1","requestKey":"k1","promptId":"p1","toolName":"write_file","toolArgs":{"path":"main.go"},"description":"write file","details":{"path":"main.go"},"rationale":"edit","operation":"write_file","paths":["main.go"],"diff":"@@","checkpointId":"cp1","changed":true,"message":"approve?","capabilities":{"diff":true},"sandboxPreset":"workspace-write"}`},
		{"PermissionRes", &PermissionRes{}, `{"requestId":"r1","requestKey":"k1","promptId":"p1","decision":"allow","allowed":true,"rememberScope":"session","approvedPaths":["main.go"],"approvedChunks":[{"id":"h1"}]}`},
		{"ToolChunk", &ToolChunk{}, `{"eventId":"e1","turnId":"r1","requestId":"r1","toolCallId":"c1","toolName":"bash","chunkIndex":1,"chunk":"out","taskId":"t1","sourceId":"s1"}`},
		{"InlineChunk", &InlineChunk{}, `{"requestId":"r1","chunk":"fmt.Println","done":false}`},
		{"CancelParams", &CancelParams{}, `{"requestId":"r1"}`},
		{"CancelResult", &CancelResult{}, `{"success":true,"requestId":"r1"}`},
		{"ProviderInfo", &ProviderInfo{}, `{"name":"openai","model":"gpt-5.4","initialized":true,"routingMode":"manual","capabilities":{"streaming":true},"supported_clients":["nvim"],"tier":"frontier","costPer1kIn":0.01,"costPer1kOut":0.03,"contextWindow":128000,"streaming":true,"vision":true,"functionCall":true}`},
		{"SwitchProviderParams", &SwitchProviderParams{}, `{"provider":"openai","model":"gpt-5.4"}`},
		{"SwitchProviderResult", &SwitchProviderResult{}, `{"success":true,"provider":{"name":"openai","model":"gpt-5.4"},"error":"none","availableProviders":["openai"]}`},
		{"ListProvidersResult", &ListProvidersResult{}, `{"openai":{"available":true,"ready":true,"statusLabel":"API key configured","models":["gpt-5.4"],"modelTiers":{"gpt-5.4":{"tier":"frontier","cost1kIn":0.01,"cost1kOut":0.03,"speedRank":1,"contextWindow":128000}},"capabilities":["streaming"]}}`},
		{"ProviderDetail", &ProviderDetail{}, `{"available":true,"ready":true,"statusLabel":"API key configured","models":["gpt-5.4"],"modelTiers":{"gpt-5.4":{"tier":"frontier","cost1kIn":0.01,"cost1kOut":0.03,"speedRank":1,"contextWindow":128000}},"capabilities":["streaming"]}`},
		{"ModelTierDetail", &ModelTierDetail{}, `{"tier":"frontier","cost1kIn":0.01,"cost1kOut":0.03,"speedRank":1,"contextWindow":128000}`},
		{"SetApiKeyParams", &SetApiKeyParams{}, `{"provider":"openai","apiKey":"sk-test","persist":true,"reloadActiveProvider":true}`},
		{"SetAPIKeyResult", &SetAPIKeyResult{}, `{"success":true,"provider":"openai","envVar":"OPENAI_API_KEY","persisted":true,"activeProviderReloaded":true,"maskedKey":"********"}`},
		{"DiffListParams", &DiffListParams{}, `{}`},
		{"DiffListResult", &DiffListResult{}, `{"edits":[{"edit_id":"e1","editId":"e1","path":"main.go","prompt":"chat fenced code block","tool_call_id":"c1","toolCallId":"c1","status":"pending","diff":"@@","original":"old","proposed":"new","hunks":[{"hunk_id":"h1","hunkId":"h1","path":"main.go","header":"@@","before":"old","after":"new","line_start":1,"lineStart":1,"status":"pending"}],"checkpoint_id":"cp1","checkpointId":"cp1"}]}`},
		{"DiffPreviewParams", &DiffPreviewParams{}, `{"editId":"e1"}`},
		{"DiffPreview", &DiffPreview{}, `{"edit_id":"e1","editId":"e1","path":"main.go","prompt":"prompt","tool_call_id":"c1","toolCallId":"c1","status":"pending","diff":"@@","original":"old","proposed":"new","hunks":[{"hunk_id":"h1","hunkId":"h1","path":"main.go","header":"@@","before":"old","after":"new","line_start":1,"lineStart":1,"status":"pending"}],"checkpoint_id":"cp1","checkpointId":"cp1"}`},
		{"HunkDetail", &HunkDetail{}, `{"hunk_id":"h1","hunkId":"h1","path":"main.go","header":"@@","before":"old","after":"new","line_start":1,"lineStart":1,"status":"pending","body":"body","added":1,"removed":1}`},
		{"DiffStageParams", &DiffStageParams{}, `{"path":"main.go","original":"old","proposed":"new","toolCallId":"c1","prompt":"prompt"}`},
		{"AcceptParams", &AcceptParams{}, `{"editId":"e1","hunkId":"h1"}`},
		{"RejectParams", &RejectParams{}, `{"editId":"e1","hunkId":"h1"}`},
		{"RegenParams", &RegenParams{}, `{"editId":"e1","hunkId":"h1","instruction":"try again","newContent":"new"}`},
		{"TimelineEvent", &TimelineEvent{}, `{"eventId":"e1","turnId":"r1","toolCallId":"c1","toolName":"bash","status":"done","argsPreview":"ls","argsFull":{"command":"ls"},"startedAt":1.25,"endedAt":2.25,"durationMs":1000,"resultPreview":"ok","resultFull":"ok","resultFullSize":2,"error":"failed","costTokens":10,"streamChunks":["o","k"],"dismissed":true,"updatedAt":3.25,"id":"e1","type":"tool_result","payload":{"x":1}}`},
		{"TimelineListParams", &TimelineListParams{}, `{"turnId":"r1","limit":200}`},
		{"TimelineListResult", &TimelineListResult{}, `{"events":[{"eventId":"e1","turnId":"r1","toolCallId":"c1","toolName":"bash","status":"done"}]}`},
		{"CancelEventParams", &CancelEventParams{}, `{"eventId":"e1"}`},
		{"RetryEventParams", &RetryEventParams{}, `{"eventId":"e1"}`},
		{"DismissEventParams", &DismissEventParams{}, `{"eventId":"e1"}`},
		{"TimelineCancelResult", &TimelineCancelResult{}, `{"cancelled":true}`},
		{"TimelineRetryResult", &TimelineRetryResult{}, `{"newEventId":"e2","ok":false,"error":"event not found"}`},
		{"TimelineDismissResult", &TimelineDismissResult{}, `{"ok":true}`},
		{"CostSnapshot", &CostSnapshot{}, `{"session":{"total_usd":0.01,"total_tokens":{"cached_read":5,"in":10,"out":5},"turns":1,"cache_hit_rate":50},"summary":{"input_tokens":10,"output_tokens":5,"total_tokens":15,"estimated_cost_usd":0.01},"per_turn":[{"cost_usd":0.01}],"perTurn":[{"costUSD":0.01}],"last_turn":{"cost_usd":0.01},"lastTurn":{"costUSD":0.01},"top_tools":[{"name":"bash"}],"topTools":[{"name":"bash"}],"projected_monthly_usd":1,"projectedMonthlyUSD":1,"projected_monthly_last_week_usd":2,"projectedMonthlyLastWeekUSD":2,"daily":{"2026-04-14":0.01},"cache":{"hits":1}}`},
		{"CostSession", &CostSession{}, `{"total_usd":0.01,"total_tokens":{"in":10},"turns":1,"cache_hit_rate":50}`},
		{"CostSummary", &CostSummary{}, `{"input_tokens":10,"output_tokens":5,"total_tokens":15,"estimated_cost_usd":0.01,"tool_filtering":{"tokens_saved":1},"tool_filtering_tokens_saved":1,"safe_pretokenization":{"tokens_saved":1},"safe_pretokenization_tokens_saved":1,"block_cache":{"hits":1},"cache_creation_input_tokens":2,"cache_read_input_tokens":3,"cache_hit_count":1,"cache_miss_count":1,"cache_hit_rate_pct":50,"estimated_cache_savings_usd":0.001,"request_count":2,"inputTokens":10,"outputTokens":5,"totalTokens":15,"estimatedCost":0.01,"toolFiltering":{"tokens_saved":1},"toolFilteringTokensSaved":1,"safePretokenization":{"tokens_saved":1},"safePretokenizationTokensSaved":1,"blockCache":{"hits":1},"cacheCreationInputTokens":2,"cacheReadInputTokens":3,"cacheHitCount":1,"cacheMissCount":1,"cacheHitRatePct":50,"estimatedCacheSavingsUSD":0.001,"requestCount":2,"sessionCost":0.01,"totalCost":0.02,"cacheReadTokens":3,"perProvider":{"openai":0.01}}`},
		{"ContextPressure", &ContextPressure{}, `{"used_tokens":10,"max_tokens":100,"pressure_pct":10,"strategy_hint":"ok","usedTokens":10,"maxTokens":100,"pressurePct":10,"budgetTokens":100,"percent":10,"warning":"ok"}`},
		{"ContextBreakdown", &ContextBreakdown{}, `{"system_tokens":1,"history_tokens":2,"tool_result_tokens":3,"total_tokens":6,"max_context_tokens":100,"pressure_pct":6,"turn_count":1,"byCategory":{"system":1},"total":6}`},
		{"SavingsSnapshot", &SavingsSnapshot{}, `{"by_source":[{"source":"prompt_caching","tokens_saved":10,"usd_saved":0.001,"methodology":"estimated"}],"all_sources":[{"source":"prompt_caching","tokens_saved":10,"usd_saved":0.001,"methodology":"estimated"}],"source_order":["prompt_caching"],"tokens_saved":10,"usd_saved":0.001,"session_delta":{"tokens_saved":10},"methodology":{"prompt_caching":"estimated"},"history":{"daily":{"2026-04-14":0.001}},"top_contributors_by_week":[{"week":"2026-W16"}],"totalSavedUsd":0.001,"byStrategy":{"prompt_caching":0.001},"lastUpdatedAt":1776100000000}`},
		{"SavingsSource", &SavingsSource{}, `{"source":"prompt_caching","tokens_saved":10,"usd_saved":0.001,"methodology":"estimated"}`},
		{"SessionSummary", &SessionSummary{}, `{"sessionId":"s1","startedAt":"2026-04-14T00:00:00Z","endedAt":"2026-04-14T00:00:00Z","model":"gpt-5.4","messageCount":2,"isActive":true,"source":"snapshot","label":"work","workingDirectory":"/repo","status":"active","createdAt":"2026-04-14T00:00:00Z","branchName":"poor-cli/session/s1","isDefault":true,"title":"work","costUsd":0.01,"updatedAt":1776100000000,"id":"s1"}`},
		{"ListSessionsResult", &ListSessionsResult{}, `{"sessions":[{"sessionId":"s1","messageCount":2}],"activeSessionId":"s1"}`},
		{"SwitchSessionParams", &SwitchSessionParams{}, `{"sessionId":"s1"}`},
		{"SwitchSessionResult", &SwitchSessionResult{}, `{"session":{"sessionId":"s1","messageCount":0},"error":"none"}`},
		{"Checkpoint", &Checkpoint{}, `{"checkpointId":"cp1","createdAt":"2026-04-14T00:00:00Z","description":"manual","operationType":"manual","fileCount":1,"totalSizeBytes":10,"tags":["manual"]}`},
		{"ListCheckpointsResult", &ListCheckpointsResult{}, `{"available":true,"checkpoints":[{"checkpointId":"cp1","createdAt":"2026-04-14T00:00:00Z","description":"manual","operationType":"manual","fileCount":1,"totalSizeBytes":10,"tags":["manual"]}],"storageSizeBytes":100,"storagePath":"/repo/.poor-cli/checkpoints"}`},
		{"McpServer", &McpServer{}, `{"name":"fs","transport":"stdio","enabled":true,"command":"node","args":["server.js"],"env":{"NODE_ENV":"test"},"url":"http://localhost","headers":{"Authorization":"Bearer test"},"tools":["fs:read"],"status":"healthy","connected":true,"toolCount":1,"lastError":"none","error":"none"}`},
		{"McpListResult", &McpListResult{}, `{"configPath":"/repo/.poor-cli/mcp.json","registryAutodiscover":true,"servers":[{"name":"fs","transport":"stdio","enabled":true}]}`},
		{"McpToggleParams", &McpToggleParams{}, `{"name":"fs","enabled":true,"confirmed":true}`},
		{"McpHealth", &McpHealth{}, `{"servers":[{"name":"fs","healthy":true}],"error":"none"}`},
		{"McpHealthServer", &McpHealthServer{}, `{"name":"fs","healthy":true}`},
		{"McpTestParams", &McpTestParams{}, `{"tool":"fs:read","toolName":"fs:read","arguments":{"path":"README.md"}}`},
		{"McpTestResult", &McpTestResult{}, `{"tool":"fs:read","result":{"ok":true}}`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if reflect.TypeOf(tt.dst).Kind() != reflect.Pointer {
				t.Fatalf("dst must be pointer")
			}
			if err := json.Unmarshal([]byte(tt.json), tt.dst); err != nil {
				t.Fatalf("unmarshal: %v", err)
			}
			out, err := json.Marshal(tt.dst)
			if err != nil {
				t.Fatalf("marshal: %v", err)
			}
			if string(out) != tt.json {
				t.Fatalf("round trip mismatch\nwant: %s\n got: %s", tt.json, out)
			}
		})
	}
}
