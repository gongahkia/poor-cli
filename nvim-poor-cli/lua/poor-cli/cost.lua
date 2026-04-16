local rpc = require("poor-cli.rpc")
local M = {}

function M.get_session_cost(params, callback) return rpc.request("poor-cli/getSessionCost", params or {}, callback) end
function M.get_economy_savings(params, callback) return rpc.request("poor-cli/getEconomySavings", params or {}, callback) end
function M.set_economy_preset(params, callback) return rpc.request("poor-cli/setEconomyPreset", params or {}, callback) end
function M.get_cost_history(params, callback) return rpc.request("poor-cli/getCostHistory", params or {}, callback) end
function M.get_tokens_visualization(params, callback) return rpc.request("poor-cli/getTokensVisualization", params or {}, callback) end
function M.get_cache_stats(params, callback) return rpc.request("poor-cli/getCacheStats", params or {}, callback) end
function M.apply_budget_template(params, callback) return rpc.request("poor-cli/applyBudgetTemplate", params or {}, callback) end
function M.list_budget_templates(params, callback) return rpc.request("poor-cli/listBudgetTemplates", params or {}, callback) end
function M.get_context_pressure(params, callback) return rpc.request("poor-cli/getContextPressure", params or {}, callback) end
function M.get_context_breakdown(params, callback) return rpc.request("poor-cli/getContextBreakdown", params or {}, callback) end
function M.compare_model_cost(params, callback) return rpc.request("poor-cli/compareModelCost", params or {}, callback) end
function M.export_cost_report(params, callback) return rpc.request("poor-cli/exportCostReport", params or {}, callback) end
function M.snapshot(params, callback) return rpc.request("cost.snapshot", params or {}, callback) end
function M.history(params, callback) return rpc.request("cost.history", params or {}, callback) end

M._snapshot = nil
M._last_snapshot_ms = 0
M._snapshot_interval_ms = 2000
M._alarm_fired = { session = 0, daily = 0 }

local function cost_config()
    local ok, cfg = pcall(require, "poor-cli.config")
    if not ok then return {} end
    return cfg.get("cost") or {}
end

function M.enabled()
    local cfg = cost_config()
    return cfg.enabled ~= false
end

local function as_number(value)
    return tonumber(value) or 0
end

local function last_turn(snapshot)
    snapshot = snapshot or {}
    local turn = snapshot.last_turn or snapshot.lastTurn
    if type(turn) == "table" and next(turn) ~= nil then return turn end
    local turns = snapshot.per_turn or snapshot.perTurn or {}
    if type(turns) == "table" and #turns > 0 then return turns[#turns] end
    return {}
end

local function session_total(snapshot)
    snapshot = snapshot or {}
    local session = snapshot.session or {}
    local summary = snapshot.summary or {}
    return as_number(session.total_usd or summary.estimated_cost_usd or summary.estimatedCost or snapshot.estimated_cost_usd or snapshot.estimatedCost)
end

local function cache_rate(snapshot)
    snapshot = snapshot or {}
    local session = snapshot.session or {}
    local summary = snapshot.summary or {}
    local cache = snapshot.cache or {}
    return as_number(session.cache_hit_rate or cache.hit_rate_pct or summary.cache_hit_rate_pct or summary.cacheHitRatePct)
end

local function today_usd(snapshot)
    local daily = (snapshot or {}).daily or {}
    local today = os.date("!%Y-%m-%d")
    return as_number(daily[today])
end

function M.format_component(snapshot)
    if not M.enabled() then return "" end
    snapshot = snapshot or M._snapshot or {}
    local total = session_total(snapshot)
    local turn = last_turn(snapshot)
    local delta = as_number(turn.cost_usd or turn.costUSD or turn.estimated_cost_usd or turn.estimatedCost)
    local cache = math.floor(cache_rate(snapshot) + 0.5)
    return string.format("$%.2f · Δ$%.2f · cache %d%%", total, delta, cache)
end

function M.component_cost()
    if not M.enabled() then return "" end
    local ok, rpc_mod = pcall(require, "poor-cli.rpc")
    if ok and rpc_mod.is_running and rpc_mod.is_running() then
        M.refresh_snapshot(false)
    end
    if not M._snapshot then return "" end
    return M.format_component(M._snapshot)
end

function M.format_turn_badge(meta)
    if not M.enabled() then return "" end
    meta = meta or {}
    local usd = as_number(meta.cost_usd or meta.estimated_cost or meta.estimatedCost)
    local seconds = as_number(meta.duration_s or meta.duration_seconds)
    if seconds <= 0 then
        seconds = as_number(meta.duration_ms or meta.durationMs) / 1000
    end
    if seconds <= 0 and meta.started_at_ns and vim.loop.hrtime then
        seconds = math.max(0, (vim.loop.hrtime() - meta.started_at_ns) / 1e9)
    end
    local tokens = as_number(meta.total_tokens or meta.totalTokens)
    if tokens <= 0 then
        tokens = as_number(meta.input_tokens or meta.inputTokens) + as_number(meta.output_tokens or meta.outputTokens)
    end
    if tokens <= 0 then tokens = as_number(meta.estimated_output_tokens or 0) end
    return string.format("[$%.2f · %.1fs · %d tok]", usd, seconds, math.floor(tokens + 0.5))
end

function M.check_alarms(snapshot)
    if not M.enabled() then return end
    local cfg = cost_config()
    local session_threshold = as_number(cfg.alarm_session)
    local daily_threshold = as_number(cfg.alarm_daily)
    local total = session_total(snapshot)
    if session_threshold > 0 and total >= session_threshold and M._alarm_fired.session < session_threshold then
        M._alarm_fired.session = session_threshold
        require("poor-cli.notify").notify(string.format("poor-cli: session cost has crossed $%.2f", session_threshold), vim.log.levels.WARN)
    end
    local daily = today_usd(snapshot)
    if daily_threshold > 0 and daily >= daily_threshold and M._alarm_fired.daily < daily_threshold then
        M._alarm_fired.daily = daily_threshold
        require("poor-cli.notify").notify(string.format("poor-cli: daily cost has crossed $%.2f", daily_threshold), vim.log.levels.WARN)
    end
end

function M.refresh_snapshot(force, callback)
    if not M.enabled() then
        M._snapshot = nil
        if callback then callback(nil) end
        return
    end
    local now = vim.loop.now()
    if not force and M._snapshot and now - M._last_snapshot_ms < M._snapshot_interval_ms then
        if callback then callback(M._snapshot) end
        return
    end
    M._last_snapshot_ms = now
    M.snapshot({}, function(result, err)
        vim.schedule(function()
            if not err and type(result) == "table" then
                M._snapshot = result
                M.check_alarms(result)
            end
            if callback then callback(M._snapshot, err) end
        end)
    end)
end

function M.setup_hud_autocmds()
    local group = vim.api.nvim_create_augroup("poor-cli-cost-hud", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLITurnEnded",
        callback = function()
            M.refresh_snapshot(true)
        end,
    })
end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function show_lines(title, content, filetype)
    local float_win = require("poor-cli.float_win")
    local lines = type(content) == "table"
        and content
        or vim.split(tostring(content), "\n", { plain = true })
    float_win.open_lines(lines, {
        filetype = filetype or "markdown",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.6,
        height = 0.6,
        position = "center",
    })
end

function M.setup()
    M.setup_hud_autocmds()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLICost", function()
        M.get_session_cost({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local block = r.blockCache or r.block_cache or {}
            local pretok = r.safePretokenization or r.safe_pretokenization or {}
            local lines = {
                "# session cost", "",
                "Input tokens: " .. tostring(r.inputTokens or 0),
                "Output tokens: " .. tostring(r.outputTokens or 0),
                "Total tokens: " .. tostring(r.totalTokens or 0),
                "Estimated cost: $" .. tostring(r.estimatedCost or r.cost or 0),
                "Cache read tokens: " .. tostring(r.cacheReadInputTokens or 0),
                "Cache write tokens: " .. tostring(r.cacheCreationInputTokens or 0),
                "Cache hit rate: " .. tostring(r.cacheHitRatePct or 0) .. "%",
                "Block cache: " .. tostring(block.hits or 0) .. " hits / " .. tostring(block.misses or 0) .. " misses (" .. tostring(block.rolling_hit_rate_pct or block.rollingHitRatePct or 0) .. "% rolling)",
                "Estimated cache savings: $" .. tostring(r.estimatedCacheSavingsUSD or 0),
                "Safe pre-tokenization: " .. tostring(pretok.tokens_saved or r.safePretokenizationTokensSaved or r.safe_pretokenization_tokens_saved or 0) .. " tokens across " .. tostring(pretok.files or 0) .. " files",
                "Requests: " .. tostring(r.requestCount or 0),
            }
            show_lines("[poor-cli cost]", lines, "markdown")
        end) end)
    end, { desc = "Show session cost" })
    create_command("PoorCLISavings", function()
        require("poor-cli.panels.savings_dashboard").open()
    end, { desc = "Open poor-cli savings dashboard" })
    create_command("PoorCLIEconomyPreset", function(opts)
        M.set_economy_preset({ preset = opts.args }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("economy preset set: " .. opts.args, vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Set economy preset" })
    create_command("PoorCLICostHistory", function()
        local pickers = require("poor-cli.pickers")
        M.get_cost_history({ limit = 20 }, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local entries = r.entries or {}
            if #entries == 0 then notify("no cost history", vim.log.levels.INFO); return end
            local items = {}
            for _, e in ipairs(entries) do
                local label = string.format("%s %s/%s $%.4f (%din/%dout)",
                    e.timestamp or "", e.provider or "", e.model or "",
                    e.cost_usd or 0, e.input_tokens or 0, e.output_tokens or 0)
                items[#items + 1] = {
                    label = label,
                    preview = vim.inspect(e),
                    data = e,
                }
            end
            local title = string.format("cost history — %d sessions, $%.2f total",
                r.count or 0, r.total_cost_usd or 0)
            pickers.pick(items, { title = title, on_pick = function(e)
                show_lines("[poor-cli cost entry]", vim.split(vim.inspect(e), "\n", { plain = true }), "lua")
            end })
        end) end)
    end, { desc = "Show session cost history" })
    create_command("PoorCLITokens", function()
        M.get_tokens_visualization({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            show_lines("[poor-cli tokens]", (result or {}).visualization or "n/a", "markdown")
        end) end)
    end, { desc = "Show context window token visualization" })
    create_command("PoorCLICacheStats", function()
        M.get_cache_stats({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local lines = { "# cache stats", "" }
            for k, v in pairs(result or {}) do table.insert(lines, k .. ": " .. tostring(v)) end
            show_lines("[poor-cli cache-stats]", lines, "markdown")
        end) end)
    end, { desc = "Show cache hit/miss stats" })
    create_command("PoorCLIBudget", function(opts)
        if opts.args == "" then
            local pickers = require("poor-cli.pickers")
            M.list_budget_templates({}, function(result, err) vim.schedule(function()
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local templates = (result or {}).templates or {}
                local items = {}
                for name, vals in pairs(templates) do
                    items[#items + 1] = {
                        id = name,
                        label = string.format("%s: %d tok / $%.2f", name, vals.session_max_tokens or 0, vals.session_max_cost_usd or 0),
                        preview = vim.inspect(vals),
                        data = { name = name, vals = vals },
                    }
                end
                if #items == 0 then notify("no budget templates", vim.log.levels.INFO); return end
                pickers.pick(items, { title = "poor-cli budget templates", on_pick = function(t)
                    M.apply_budget_template({ template = t.name }, function(_, e) vim.schedule(function()
                        if e then notify(rpc.format_error(e), vim.log.levels.ERROR)
                        else notify("budget template applied: " .. t.name, vim.log.levels.INFO) end
                    end) end)
                end })
            end) end)
        else
            M.apply_budget_template({ template = opts.args }, function(_, err) vim.schedule(function()
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                else notify("budget template applied: " .. opts.args, vim.log.levels.INFO) end
            end) end)
        end
    end, { nargs = "?", desc = "List or apply budget template" })
    create_command("PoorCLIPressure", function()
        M.get_context_pressure({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local r = result or {}
            notify(string.format("context pressure: %.1f%% (%d/%d tok) hint: %s",
                r.pressure_pct or 0, r.used_tokens or 0, r.max_tokens or 0, r.strategy_hint or "ok"),
                vim.log.levels.INFO)
        end) end)
    end, { desc = "Show context window pressure" })
    create_command("PoorCLIBreakdown", function()
        M.get_context_breakdown({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = {
                "# context breakdown (" .. string.format("%.1f", r.pressure_pct or 0) .. "% used)", "",
                "system:  " .. tostring(r.system_tokens or 0) .. " tok",
                "history: " .. tostring(r.history_tokens or 0) .. " tok",
                "tools:   " .. tostring(r.tool_result_tokens or 0) .. " tok",
                "total:   " .. tostring(r.total_tokens or 0) .. " / " .. tostring(r.max_context_tokens or 0) .. " tok",
                "turns:   " .. tostring(r.turn_count or 0),
            }
            show_lines("[poor-cli breakdown]", lines, "markdown")
        end) end)
    end, { desc = "Show context window breakdown by category" })
    create_command("PoorCLICompareCost", function(opts)
        local parts = vim.split(opts.args, " ", { plain = true })
        if #parts < 2 then notify("usage: PoorCLICompareCost <provider> <model>", vim.log.levels.WARN); return end
        M.compare_model_cost({ provider = parts[1], model = parts[2] }, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            if result.error then notify(result.error, vim.log.levels.WARN); return end
            local lines = {
                "# model cost comparison", "",
                "current: " .. (result.current or {}).provider .. "/" .. (result.current or {}).model,
                "target:  " .. (result.target or {}).provider .. "/" .. (result.target or {}).model,
                "input ratio:  " .. tostring(result.input_cost_ratio or 0) .. "x",
                "output ratio: " .. tostring(result.output_cost_ratio or 0) .. "x",
                "session cost so far: $" .. tostring(result.session_cost_current_usd or 0),
                "if target model:     $" .. tostring(result.session_cost_if_target_usd or 0),
            }
            show_lines("[poor-cli compare]", lines, "markdown")
        end) end)
    end, { nargs = "+", desc = "Compare model costs" })
    create_command("PoorCLIExportCost", function()
        M.export_cost_report({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            show_lines("[poor-cli cost-export]", (vim.json and vim.json.encode or vim.fn.json_encode)(result), "json")
        end) end)
    end, { desc = "Export full cost report" })
end

return M
