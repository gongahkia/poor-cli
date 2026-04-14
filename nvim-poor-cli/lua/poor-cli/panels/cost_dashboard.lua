local config = require("poor-cli.config")
local cost = require("poor-cli.cost")

local M = {}

M.buf = nil
M.win = nil
M.snapshot = nil

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
    vim.cmd("botright 88vsplit")
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = true
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.keymap.set("n", "q", function()
        if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
        M.win = nil
    end, { buffer = M.buf, nowait = true, desc = "Close cost dashboard" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "Refresh cost dashboard" })
    vim.keymap.set("n", "e", M.export_json, { buffer = M.buf, nowait = true, desc = "Export cost dashboard JSON" })
    M.refresh()
    return M.buf
end

return M
