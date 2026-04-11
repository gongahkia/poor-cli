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

local function open_scratch(title, content, filetype)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = filetype or "markdown"
    vim.api.nvim_buf_set_name(buf, title)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(content, "\n", { plain = true }))
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
    return buf
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCliCost", function()
        M.get_session_cost({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = {
                "# session cost", "",
                "Input tokens: " .. tostring(r.inputTokens or 0),
                "Output tokens: " .. tostring(r.outputTokens or 0),
                "Total tokens: " .. tostring(r.totalTokens or 0),
                "Estimated cost: $" .. tostring(r.estimatedCost or r.cost or 0),
                "Cache read tokens: " .. tostring(r.cacheReadInputTokens or 0),
                "Cache write tokens: " .. tostring(r.cacheCreationInputTokens or 0),
                "Cache hit rate: " .. tostring(r.cacheHitRatePct or 0) .. "%",
                "Estimated cache savings: $" .. tostring(r.estimatedCacheSavingsUSD or 0),
                "Requests: " .. tostring(r.requestCount or 0),
            }
            open_scratch("[poor-cli cost]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "Show session cost" })
    create_command("PoorCliSavings", function()
        M.get_economy_savings({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = {
                "# economy savings", "",
                "Preset: " .. tostring(r.preset or "none"),
                "Tokens saved: " .. tostring(r.tokensSaved or 0),
                "Cost saved: $" .. tostring(r.costSaved or 0),
                "Cache hits: " .. tostring(r.cacheHits or 0),
            }
            open_scratch("[poor-cli savings]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "Show economy savings" })
    create_command("PoorCliEconomyPreset", function(opts)
        M.set_economy_preset({ preset = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] economy preset set: " .. opts.args, vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Set economy preset" })
    create_command("PoorCliCostHistory", function()
        M.get_cost_history({ limit = 20 }, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = { "# cost history (" .. tostring(r.count or 0) .. " sessions, $" .. tostring(r.total_cost_usd or 0) .. " total)", "" }
            for _, e in ipairs(r.entries or {}) do
                table.insert(lines, string.format("  %s %s/%s $%.4f (%din/%dout)", e.timestamp or "", e.provider or "", e.model or "", e.cost_usd or 0, e.input_tokens or 0, e.output_tokens or 0))
            end
            open_scratch("[poor-cli cost-history]", table.concat(lines, "\n"))
        end) end)
    end, { desc = "Show session cost history" })
    create_command("PoorCliTokens", function()
        M.get_tokens_visualization({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli tokens]", result.visualization or "n/a")
        end) end)
    end, { desc = "Show context window token visualization" })
    create_command("PoorCliCacheStats", function()
        M.get_cache_stats({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local lines = { "# cache stats", "" }
            for k, v in pairs(result or {}) do table.insert(lines, k .. ": " .. tostring(v)) end
            open_scratch("[poor-cli cache-stats]", table.concat(lines, "\n"))
        end) end)
    end, { desc = "Show cache hit/miss stats" })
    create_command("PoorCliBudget", function(opts)
        if opts.args == "" then
            M.list_budget_templates({}, function(result, err) vim.schedule(function()
                if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                local lines = { "# budget templates", "" }
                for name, vals in pairs(result.templates or {}) do
                    table.insert(lines, string.format("  %s: %d tok / $%.2f", name, vals.session_max_tokens or 0, vals.session_max_cost_usd or 0))
                end
                open_scratch("[poor-cli budgets]", table.concat(lines, "\n"))
            end) end)
        else
            M.apply_budget_template({ template = opts.args }, function(_, err) vim.schedule(function()
                if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else vim.notify("[poor-cli] budget template applied: " .. opts.args, vim.log.levels.INFO) end
            end) end)
        end
    end, { nargs = "?", desc = "List or apply budget template" })
    create_command("PoorCliPressure", function()
        M.get_context_pressure({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local r = result or {}
            vim.notify(string.format("[poor-cli] context pressure: %.1f%% (%d/%d tok) hint: %s", r.pressure_pct or 0, r.used_tokens or 0, r.max_tokens or 0, r.strategy_hint or "ok"), vim.log.levels.INFO)
        end) end)
    end, { desc = "Show context window pressure" })
    create_command("PoorCliBreakdown", function()
        M.get_context_breakdown({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = {
                "# context breakdown (" .. string.format("%.1f", r.pressure_pct or 0) .. "% used)", "",
                "system:  " .. tostring(r.system_tokens or 0) .. " tok",
                "history: " .. tostring(r.history_tokens or 0) .. " tok",
                "tools:   " .. tostring(r.tool_result_tokens or 0) .. " tok",
                "total:   " .. tostring(r.total_tokens or 0) .. " / " .. tostring(r.max_context_tokens or 0) .. " tok",
                "turns:   " .. tostring(r.turn_count or 0),
            }
            open_scratch("[poor-cli breakdown]", table.concat(lines, "\n"))
        end) end)
    end, { desc = "Show context window breakdown by category" })
    create_command("PoorCliCompareCost", function(opts)
        local parts = vim.split(opts.args, " ", { plain = true })
        if #parts < 2 then vim.notify("[poor-cli] usage: PoorCliCompareCost <provider> <model>", vim.log.levels.WARN); return end
        M.compare_model_cost({ provider = parts[1], model = parts[2] }, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            if result.error then vim.notify("[poor-cli] " .. result.error, vim.log.levels.WARN); return end
            local lines = {
                "# model cost comparison", "",
                "current: " .. (result.current or {}).provider .. "/" .. (result.current or {}).model,
                "target:  " .. (result.target or {}).provider .. "/" .. (result.target or {}).model,
                "input ratio:  " .. tostring(result.input_cost_ratio or 0) .. "x",
                "output ratio: " .. tostring(result.output_cost_ratio or 0) .. "x",
                "session cost so far: $" .. tostring(result.session_cost_current_usd or 0),
                "if target model:     $" .. tostring(result.session_cost_if_target_usd or 0),
            }
            open_scratch("[poor-cli compare]", table.concat(lines, "\n"))
        end) end)
    end, { nargs = "+", desc = "Compare model costs" })
    create_command("PoorCliExportCost", function()
        M.export_cost_report({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli cost-export]", vim.fn.json_encode(result), "json")
        end) end)
    end, { desc = "Export full cost report" })
end

return M
