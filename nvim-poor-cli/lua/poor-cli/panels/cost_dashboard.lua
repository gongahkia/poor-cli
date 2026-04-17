local config = require("poor-cli.config")
local cost = require("poor-cli.cost")
local rpc = require("poor-cli.rpc")

local M = {}

M.buf = nil
M.win = nil
M.snapshot = nil
M.savings = nil

local blocks = { "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█" }

local function enabled()
    local cfg = config.get("cost") or {}
    return cfg.enabled ~= false
end

local function n(value)
    return tonumber(value) or 0
end

local function usd(value)
    return string.format("$%.2f", n(value))
end

local function usd4(value)
    return string.format("$%.4f", n(value))
end

local function source_label(source)
    return tostring(source or ""):gsub("_", " ")
end

local function sorted_days(daily)
    local days = {}
    for day, _ in pairs(daily or {}) do table.insert(days, day) end
    table.sort(days)
    return days
end

local function history_values(history)
    local daily = (history or {}).daily or {}
    local values = {}
    for _, day in ipairs(sorted_days(daily)) do table.insert(values, n(daily[day])) end
    return values
end

local function pct(value)
    return string.format("%.0f%%", n(value))
end

local function sorted_turns(snapshot)
    local turns = snapshot.per_turn or snapshot.perTurn or {}
    local out = {}
    for _, turn in ipairs(turns) do table.insert(out, turn) end
    return out
end

function M.sparkline(values)
    if #values == 0 then return "n/a" end
    local max = 0
    for _, value in ipairs(values) do
        if n(value) > max then max = n(value) end
    end
    if max <= 0 then return string.rep(blocks[1], #values) end
    local chars = {}
    for _, value in ipairs(values) do
        local idx = math.max(1, math.min(#blocks, math.ceil((n(value) / max) * #blocks)))
        table.insert(chars, blocks[idx])
    end
    return table.concat(chars, "")
end

function M.render_lines(snapshot)
    snapshot = snapshot or {}
    local session = snapshot.session or {}
    local summary = snapshot.summary or {}
    local cache = snapshot.cache or {}
    local turns = sorted_turns(snapshot)
    local costs = {}
    for _, turn in ipairs(turns) do table.insert(costs, n(turn.cost_usd or turn.costUSD)) end
    local total_tokens = session.total_tokens or {}
    local top_tools = snapshot.top_tools or snapshot.topTools or {}
    local lines = {
        "# poor-cli Cost Dashboard",
        "",
        "Press q to close, r to refresh, e to export JSON.",
        "",
        "## Session",
        "",
        string.format("| total | delta | turns | tokens | cache |"),
        string.format("|---:|---:|---:|---:|---:|"),
        string.format(
            "| %s | %s | %d | %d | %s |",
            usd(session.total_usd or summary.estimated_cost_usd or summary.estimatedCost),
            usd((snapshot.last_turn or snapshot.lastTurn or {}).cost_usd),
            n(session.turns or #turns),
            n((type(total_tokens) == "table" and (total_tokens["in"] or 0) + (total_tokens.out or 0)) or summary.total_tokens or summary.totalTokens),
            pct(session.cache_hit_rate or cache.hit_rate_pct or summary.cache_hit_rate_pct or summary.cacheHitRatePct)
        ),
        "",
        "## $/turn",
        "",
        M.sparkline(costs),
        "",
        "## Top tools",
        "",
    }
    if #top_tools == 0 then
        table.insert(lines, "_no tool cost surface yet_")
    else
        for i, tool in ipairs(top_tools) do
            if i > 10 then break end
            table.insert(lines, string.format("%2d. %-24s %s  %d tok  %d call(s)", i, tostring(tool.tool or tool.name or "?"), usd(tool.cost_usd or tool.costUSD), n(tool.tokens), n(tool.calls)))
        end
    end
    vim.list_extend(lines, {
        "",
        "## Cache",
        "",
        string.format("- hit rate: %s", pct(cache.hit_rate_pct or session.cache_hit_rate or summary.cache_hit_rate_pct or summary.cacheHitRatePct)),
        string.format("- hits/misses: %d/%d", n(cache.hits or summary.cache_hit_count or summary.cacheHitCount), n(cache.misses or summary.cache_miss_count or summary.cacheMissCount)),
        string.format("- read/write tokens: %d/%d", n(cache.read_tokens or summary.cache_read_input_tokens or summary.cacheReadInputTokens), n(cache.write_tokens or summary.cache_creation_input_tokens or summary.cacheCreationInputTokens)),
    })
    local by_provider = cache.by_provider or cache.byProvider
    if type(by_provider) == "table" and not vim.tbl_isempty(by_provider) then
        table.insert(lines, "")
        table.insert(lines, "### Per-provider cache")
        table.insert(lines, "")
        local names = {}
        for name, _ in pairs(by_provider) do names[#names + 1] = name end
        table.sort(names)
        for _, name in ipairs(names) do
            local stats = by_provider[name] or {}
            table.insert(lines, string.format(
                "- %-12s hit-rate=%s  hits/misses=%d/%d  read=%d  write=%d  saved=%s",
                name,
                pct(stats.hit_rate_pct),
                n(stats.hits), n(stats.misses),
                n(stats.read_tokens), n(stats.write_tokens),
                usd(stats.savings_usd)
            ))
        end
    end
    local savings = M.savings or {}
    local history = savings.history or {}
    local saved_values = history_values(history)
    local sources = savings.all_sources or savings.by_source or {}
    local session_delta = savings.session_delta or {}
    table.insert(lines, "")
    table.insert(lines, "## Savings")
    table.insert(lines, "")
    if savings.error then
        table.insert(lines, "_" .. tostring(savings.error) .. "_")
    else
        table.insert(lines, string.format(
            "- session delta: %d tokens saved, %s not spent",
            n(session_delta.tokens_saved or savings.tokens_saved),
            usd4(session_delta.usd_saved or savings.usd_saved)
        ))
        if n(session_delta.tokens_before) > 0 or n(session_delta.tokens_after) > 0 then
            table.insert(lines, string.format(
                "- before/after tokens: %d -> %d",
                n(session_delta.tokens_before), n(session_delta.tokens_after)
            ))
        end
        if #sources > 0 then
            table.insert(lines, "")
            table.insert(lines, "| source | tokens | USD | methodology |")
            table.insert(lines, "|---|---:|---:|---|")
            for _, item in ipairs(sources) do
                table.insert(lines, string.format(
                    "| %s | %d | %s | %s |",
                    source_label(item.source),
                    n(item.tokens_saved),
                    usd4(item.usd_saved),
                    tostring(item.methodology or "")
                ))
            end
        end
        if #saved_values > 0 then
            table.insert(lines, "")
            table.insert(lines, string.format("30-day: %s  (%d day%s)", M.sparkline(saved_values), #saved_values, #saved_values == 1 and "" or "s"))
        end
    end
    vim.list_extend(lines, {
        "",
        "## Projection",
        "",
        string.format("- current daily rate: %s/month", usd(snapshot.projected_monthly_usd or snapshot.projectedMonthlyUSD)),
        string.format("- last-week average: %s/month", usd(snapshot.projected_monthly_last_week_usd or snapshot.projectedMonthlyLastWeekUSD)),
    })
    return lines
end

local function render()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    local lines
    if not enabled() then
        lines = { "# poor-cli Cost Dashboard", "", "_cost HUD disabled_" }
    elseif not M.snapshot then
        lines = { "# poor-cli Cost Dashboard", "", "_loading..._" }
    else
        lines = M.render_lines(M.snapshot)
    end
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
end

function M.refresh()
    render()
    if not enabled() then return end
    cost.refresh_snapshot(true, function(snapshot, err)
        if err then
            M.snapshot = { error = tostring(err.message or err) }
        else
            M.snapshot = snapshot or {}
        end
        render()
    end)
    rpc.request("savings.snapshot", { days = 30 }, function(result, err)
        vim.schedule(function()
            if err then
                M.savings = { error = rpc.format_error(err), by_source = {}, history = { daily = {} } }
            else
                M.savings = result or {}
            end
            render()
        end)
    end)
end

function M.jump_to_savings()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf) and M.win and vim.api.nvim_win_is_valid(M.win)) then
        return
    end
    local lines = vim.api.nvim_buf_get_lines(M.buf, 0, -1, false)
    for i, line in ipairs(lines) do
        if line == "## Savings" then
            pcall(vim.api.nvim_win_set_cursor, M.win, { i, 0 })
            return
        end
    end
end

function M.export_json()
    if not M.snapshot then return end
    local encode = vim.json and vim.json.encode or vim.fn.json_encode
    local dir = vim.fs.joinpath(config.get_state_dir(), "exports")
    vim.fn.mkdir(dir, "p")
    local path = vim.fs.joinpath(dir, "cost-dashboard-" .. os.date("!%Y%m%dT%H%M%SZ") .. ".json")
    local file = io.open(path, "w")
    if not file then
        require("poor-cli.notify").notify("[poor-cli] cost dashboard export failed", vim.log.levels.ERROR)
        return
    end
    file:write(encode(M.snapshot))
    file:close()
    require("poor-cli.notify").notify("[poor-cli] exported " .. path, vim.log.levels.INFO)
end

function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return M.buf
    end
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli cost dashboard]")
    end
    local float_win = require("poor-cli.float_win")
    M.win = float_win.open(M.buf, {
        width = math.min(100, vim.o.columns - 4),
        height = math.min(30, vim.o.lines - 4),
        position = "center",
        title = " poor-cli cost dashboard ",
        close_keys = {},
        wrap = true,
    })
    local function close()
        if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
        M.win = nil
    end
    vim.keymap.set("n", "q", close, { buffer = M.buf, nowait = true, desc = "Close cost dashboard" })
    vim.keymap.set("n", "<Esc>", close, { buffer = M.buf, nowait = true, desc = "Close cost dashboard" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "Refresh cost dashboard" })
    vim.keymap.set("n", "e", M.export_json, { buffer = M.buf, nowait = true, desc = "Export cost dashboard JSON" })
    M.refresh()
    return M.buf
end

return M
