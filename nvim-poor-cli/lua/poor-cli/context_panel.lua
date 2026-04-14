local rpc = require("poor-cli.rpc")

local M = {}

M.buf = nil
M.win = nil
M.snapshot = nil
M.filter = ""
M.line_rows = {}
M.ns = vim.api.nvim_create_namespace("poor-cli_context_panel")
M.widths = { path = 44, tokens = 8, reason = 20, compressed = 10, pinned = 8 }

local function n(value)
    return tonumber(value) or 0
end

local function truncate(text, width)
    text = tostring(text or ""):gsub("\n.*", "")
    if #text <= width then return text end
    return text:sub(1, math.max(1, width - 3)) .. "..."
end

local function pad(text, width)
    text = truncate(text, width)
    return text .. string.rep(" ", math.max(0, width - #text))
end

local function badge(enabled, label)
    return enabled and label or ""
end

local function file_matches(file, filter)
    filter = tostring(filter or "")
    if filter == "" then return true end
    return tostring(file.path or ""):lower():find(filter:lower(), 1, true) ~= nil
end

local function normalized_file(file)
    file = file or {}
    return {
        path = tostring(file.path or ""),
        tokens = n(file.tokens or file.tokenEstimate or file.estimatedTokens),
        reason = tostring(file.reason or file.source or "selected"),
        compressed = file.compressed == true,
        pinned = file.pinned == true,
    }
end

local function row(file)
    return table.concat({
        pad(file.path, M.widths.path),
        pad(file.tokens, M.widths.tokens),
        pad(file.reason, M.widths.reason),
        pad(badge(file.compressed, "[cmp]"), M.widths.compressed),
        pad(badge(file.pinned, "[pin]"), M.widths.pinned),
    }, " ")
end

function M.render_lines(snapshot, filter)
    snapshot = snapshot or {}
    local files = snapshot.files or {}
    local title = string.format(
        "ContextSnapshot turn=%s budget=%d used=%d",
        tostring(snapshot.turnId or snapshot.turn_id or "?"),
        n(snapshot.budget or snapshot.budgetTokens),
        n(snapshot.used or snapshot.totalTokens)
    )
    local lines = {
        title,
        "keys: p pin/unpin  d drop  r refresh  / filter  o open  q close",
        table.concat({
            pad("path", M.widths.path),
            pad("tokens", M.widths.tokens),
            pad("reason", M.widths.reason),
            pad("compressed", M.widths.compressed),
            pad("pinned", M.widths.pinned),
        }, " "),
        string.rep("-", M.widths.path + M.widths.tokens + M.widths.reason + M.widths.compressed + M.widths.pinned + 4),
    }
    local rows = {}
    for _, raw in ipairs(files) do
        local file = normalized_file(raw)
        if file_matches(file, filter) then
            table.insert(lines, row(file))
            rows[#lines] = file
        end
    end
    if #files == 0 then
        table.insert(lines, "no context files")
    elseif vim.tbl_isempty(rows) then
        table.insert(lines, "no context files match filter")
    end
    return lines, rows
end

local function apply_badges()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    for line, file in pairs(M.line_rows) do
        local marks = {}
        if file.compressed then table.insert(marks, { "[cmp]", "Comment" }) end
        if file.pinned then table.insert(marks, { "[pin]", "Special" }) end
        if #marks > 0 then
            vim.api.nvim_buf_set_extmark(M.buf, M.ns, line - 1, 0, { virt_text = marks, virt_text_pos = "eol" })
        end
    end
end

function M.render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local lines
    lines, M.line_rows = M.render_lines(M.snapshot or {}, M.filter)
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
    apply_badges()
end

local function current_file()
    if not (M.win and vim.api.nvim_win_is_valid(M.win)) then return nil end
    local line = vim.api.nvim_win_get_cursor(M.win)[1]
    return M.line_rows[line]
end

local function set_snapshot(result, err)
    vim.schedule(function()
        if err then
            require("poor-cli.notify").notify("[poor-cli] context: " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        M.snapshot = result or {}
        M.render()
    end)
end

function M.refresh()
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) and not M.snapshot then
        vim.bo[M.buf].modifiable = true
        vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, { "ContextSnapshot", "", "loading..." })
        vim.bo[M.buf].modifiable = false
    end
    rpc.context_refresh({}, set_snapshot)
end

function M.load()
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) and not M.snapshot then
        vim.bo[M.buf].modifiable = true
        vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, { "ContextSnapshot", "", "loading..." })
        vim.bo[M.buf].modifiable = false
    end
    rpc.context_snapshot({}, set_snapshot)
end

function M.pin_current()
    local file = current_file()
    if not file then return end
    rpc.context_pin({ path = file.path }, set_snapshot)
end

function M.drop_current()
    local file = current_file()
    if not file then return end
    rpc.context_drop({ path = file.path }, set_snapshot)
end

function M.filter_prompt()
    vim.ui.input({ prompt = "context filter: ", default = M.filter }, function(input)
        if input == nil then return end
        M.filter = input
        M.render()
    end)
end

function M.open_current()
    local file = current_file()
    if not file or file.path == "" then return end
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        vim.cmd("wincmd p")
        if vim.api.nvim_get_current_win() == M.win then
            vim.cmd("leftabove split")
        end
    end
    vim.cmd("edit " .. vim.fn.fnameescape(file.path))
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_win_close(M.win, true)
    end
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
        vim.bo[M.buf].filetype = "poor-cli-context"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli context]")
    end
    vim.cmd("botright 88vsplit")
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = false
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true, desc = "Close context panel" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "Refresh context panel" })
    vim.keymap.set("n", "p", M.pin_current, { buffer = M.buf, nowait = true, desc = "Pin context file" })
    vim.keymap.set("n", "d", M.drop_current, { buffer = M.buf, nowait = true, desc = "Drop context file" })
    vim.keymap.set("n", "/", M.filter_prompt, { buffer = M.buf, nowait = true, desc = "Filter context panel" })
    vim.keymap.set("n", "o", M.open_current, { buffer = M.buf, nowait = true, desc = "Open context file" })
    M.load()
    return M.buf
end

return M
