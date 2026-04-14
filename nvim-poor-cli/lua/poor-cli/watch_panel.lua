local rpc = require("poor-cli.rpc")

local M = {}

M.buf = nil
M.win = nil
M.snapshot = nil
M.line_rows = {}
M.ns = vim.api.nvim_create_namespace("poor-cli_watch_panel")
M.limit = 20
M.widths = { path = 42, change = 24, match = 20, action = 18, outcome = 14, duration = 8 }

local function clip(value, width)
    local text = tostring(value or ""):gsub("\n.*", "")
    if #text <= width then return text end
    return text:sub(1, math.max(1, width - 3)) .. "..."
end

local function pad(value, width)
    local text = clip(value, width)
    return text .. string.rep(" ", math.max(0, width - #text))
end

local function watch_row(watch)
    return table.concat({
        pad(watch.path, M.widths.path),
        pad(watch.last_change_at, M.widths.change),
        pad(watch.last_match, M.widths.match),
    }, " ")
end

local function action_row(action)
    return table.concat({
        pad(action.at, M.widths.change),
        pad(action.trigger_path, M.widths.path),
        pad(action.action, M.widths.action),
        pad(action.outcome, M.widths.outcome),
        pad(action.duration_ms, M.widths.duration),
    }, " ")
end

function M.render_lines(snapshot)
    snapshot = snapshot or {}
    local lines = {
        "# poor-cli watch",
        "qa: " .. (snapshot.qa_enabled and "enabled" or "disabled"),
        "keys: r refresh  o open target  q close",
        "",
        "## watches",
        table.concat({ pad("path", M.widths.path), pad("last_change", M.widths.change), pad("matched_ignore", M.widths.match) }, " "),
    }
    local rows = {}
    local watches = type(snapshot.watches) == "table" and snapshot.watches or {}
    for _, watch in ipairs(watches) do
        table.insert(lines, watch_row(watch))
        rows[#lines] = { kind = "watch", path = tostring(watch.path or ""), ignored = watch.ignored == true }
    end
    if #watches == 0 then table.insert(lines, "no active watches") end
    table.insert(lines, "")
    table.insert(lines, "## recent actions")
    table.insert(lines, table.concat({
        pad("at", M.widths.change),
        pad("trigger_path", M.widths.path),
        pad("action", M.widths.action),
        pad("outcome", M.widths.outcome),
        pad("ms", M.widths.duration),
    }, " "))
    local actions = type(snapshot.recent_actions) == "table" and snapshot.recent_actions or {}
    for _, action in ipairs(actions) do
        table.insert(lines, action_row(action))
        rows[#lines] = { kind = "action", path = tostring(action.trigger_path or "") }
    end
    if #actions == 0 then table.insert(lines, "no recent actions") end
    return lines, rows
end

local function apply_highlights()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    for line, row in pairs(M.line_rows) do
        if row.ignored then
            vim.api.nvim_buf_set_extmark(M.buf, M.ns, line - 1, 0, {
                line_hl_group = "Comment",
            })
        end
    end
end

function M.render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local lines
    lines, M.line_rows = M.render_lines(M.snapshot or {})
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
    apply_highlights()
end

local function set_snapshot(result, err)
    vim.schedule(function()
        if err then
            require("poor-cli.notify").notify("[poor-cli] watch: " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        M.snapshot = result or {}
        M.render()
    end)
end

function M.refresh()
    rpc.watch_status({ limit = M.limit }, set_snapshot)
end

local function current_row()
    if not (M.win and vim.api.nvim_win_is_valid(M.win)) then return nil end
    return M.line_rows[vim.api.nvim_win_get_cursor(M.win)[1]]
end

function M.open_current()
    local row = current_row()
    if not row or row.path == "" then return end
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        vim.cmd("wincmd p")
        if vim.api.nvim_get_current_win() == M.win then vim.cmd("leftabove split") end
    end
    vim.cmd("edit " .. vim.fn.fnameescape(row.path))
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
    M.win = nil
end

function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return M.buf
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "poor-cli-watch"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli watch]")
    end
    vim.cmd("botright 92vsplit")
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = false
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true, desc = "Close watch panel" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "Refresh watch panel" })
    vim.keymap.set("n", "o", M.open_current, { buffer = M.buf, nowait = true, desc = "Open watch target" })
    M.refresh()
    return M.buf
end

return M
