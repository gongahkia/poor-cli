local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")

local M = {}

M.buf = nil
M.win = nil
M.snapshot = nil

local blocks = { "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█" }

local function n(value)
    return tonumber(value) or 0
end

local function usd(value)
    return string.format("$%.4f", n(value))
end

local function sorted_days(daily)
    local days = {}
    for day, _ in pairs(daily or {}) do table.insert(days, day) end
    table.sort(days)
    return days
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

local function history_values(history)
    local daily = (history or {}).daily or {}
    local values = {}
    for _, day in ipairs(sorted_days(daily)) do table.insert(values, n(daily[day])) end
    return values
end

local function source_label(source)
    return tostring(source or ""):gsub("_", " ")
end

function M.render_lines(snapshot)
    snapshot = snapshot or {}
    local history = snapshot.history or {}
    local values = history_values(history)
    local sources = snapshot.all_sources or snapshot.by_source or {}
    local lines = {
        "# poor-cli Savings Dashboard",
        "",
        "Estimates only. Press q to close, r to refresh, c for Cost Dashboard.",
        "",
        "## Session delta",
        "",
        string.format(
            "- %d tokens saved, %s not spent",
            n((snapshot.session_delta or {}).tokens_saved or snapshot.tokens_saved),
            usd((snapshot.session_delta or {}).usd_saved or snapshot.usd_saved)
        ),
        string.format(
            "- before/after tokens: %d -> %d",
            n((snapshot.session_delta or {}).tokens_before),
            n((snapshot.session_delta or {}).tokens_after)
        ),
        "",
        "## By source",
        "",
        "| source | tokens | USD | methodology |",
        "|---|---:|---:|---|",
    }
    for _, item in ipairs(sources) do
        table.insert(lines, string.format(
            "| %s | %d | %s | %s |",
            source_label(item.source),
            n(item.tokens_saved),
            usd(item.usd_saved),
            tostring(item.methodology or "")
        ))
    end
    vim.list_extend(lines, {
        "",
        "## 30-day savings",
        "",
        M.sparkline(values),
        "",
    })
    if #values < 30 then
        table.insert(lines, string.format("_history has %d day(s); sparkline uses available data_", #values))
        table.insert(lines, "")
    end
    table.insert(lines, "## Weekly top contributors")
    table.insert(lines, "")
    local weeks = snapshot.top_contributors_by_week or history.top_contributors_by_week or {}
    if #weeks == 0 then
        table.insert(lines, "_no persisted savings history yet_")
    else
        for _, week in ipairs(weeks) do
            local parts = {}
            for _, item in ipairs(week.top or {}) do
                table.insert(parts, source_label(item.source) .. " " .. usd(item.usd_saved))
            end
            table.insert(lines, string.format("- %s: %s", tostring(week.week or ""), table.concat(parts, ", ")))
        end
    end
    vim.list_extend(lines, {
        "",
        "## Navigation",
        "",
        "- `:PoorCLICostDashboard`",
    })
    return lines
end

local function render()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    local lines
    if not M.snapshot then
        lines = { "# poor-cli Savings Dashboard", "", "_loading..._" }
    else
        lines = M.render_lines(M.snapshot)
    end
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
end

function M.refresh()
    render()
    rpc.request("savings.snapshot", { days = 30 }, function(result, err)
        vim.schedule(function()
            if err then
                M.snapshot = { error = rpc.format_error(err), by_source = {}, history = { daily = {} } }
            else
                M.snapshot = result or {}
            end
            render()
        end)
    end)
end

function M.open_cost()
    vim.cmd("PoorCLICostDashboard")
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
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli savings dashboard]")
    end
    local width = tonumber((config.get("panels") or {}).savings_width) or 88
    vim.cmd("botright " .. tostring(width) .. "vsplit")
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = true
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.keymap.set("n", "q", function()
        if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
        M.win = nil
    end, { buffer = M.buf, nowait = true, desc = "Close savings dashboard" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "Refresh savings dashboard" })
    vim.keymap.set("n", "c", M.open_cost, { buffer = M.buf, nowait = true, desc = "Open cost dashboard" })
    M.refresh()
    return M.buf
end

return M
