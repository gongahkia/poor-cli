-- poor-cli/context_panel.lua
-- 2-pane context browser. Left = filterable file list. Right = preview of the
-- focused file with real syntax highlighting via :edit. Filter row at the top
-- of the list pane narrows incrementally as you type.

local rpc = require("poor-cli.rpc")

local M = {}

M.list_buf = nil
M.list_win = nil
M.preview_buf = nil
M.preview_win = nil
M.filter_buf = nil
M.filter_win = nil

M.snapshot = nil
M.filter = ""
M.line_rows = {}
M.ns = vim.api.nvim_create_namespace("poor-cli_context_panel")
M.widths = { path = 44, tokens = 8, reason = 18, flags = 10 }
M._preview_cache = {} -- path -> lines
M._active_path = nil

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

local function flags(file)
    local parts = {}
    if file.pinned then table.insert(parts, "pin") end
    if file.compressed then table.insert(parts, "cmp") end
    return table.concat(parts, "/")
end

-- ───────────────── renderers ─────────────────

local function render_list()
    if not (M.list_buf and vim.api.nvim_buf_is_valid(M.list_buf)) then return end
    local snap = M.snapshot or {}
    local files = snap.files or {}
    local title = string.format("turn=%s budget=%d used=%d (%s matches)",
        tostring(snap.turnId or snap.turn_id or "?"),
        n(snap.budget or snap.budgetTokens),
        n(snap.used or snap.totalTokens),
        "?") -- filled below
    local header = table.concat({
        pad("path", M.widths.path),
        pad("tokens", M.widths.tokens),
        pad("reason", M.widths.reason),
        pad("flags", M.widths.flags),
    }, " ")
    local sep = string.rep("-", M.widths.path + M.widths.tokens + M.widths.reason + M.widths.flags + 3)

    local rows = {}
    local lines = { title, header, sep }
    for _, raw in ipairs(files) do
        local file = normalized_file(raw)
        if file_matches(file, M.filter) then
            local row_line = table.concat({
                pad(file.path, M.widths.path),
                pad(tostring(file.tokens), M.widths.tokens),
                pad(file.reason, M.widths.reason),
                pad(flags(file), M.widths.flags),
            }, " ")
            table.insert(lines, row_line)
            rows[#lines] = file
        end
    end
    -- patch title with match count
    local total = 0
    for _ in pairs(rows) do total = total + 1 end
    lines[1] = string.format("turn=%s budget=%d used=%d (%d/%d)",
        tostring(snap.turnId or snap.turn_id or "?"),
        n(snap.budget or snap.budgetTokens),
        n(snap.used or snap.totalTokens),
        total, #files)

    if #files == 0 then
        table.insert(lines, "no context files")
    elseif total == 0 then
        table.insert(lines, "no files match filter")
    end

    M.line_rows = rows
    vim.bo[M.list_buf].modifiable = true
    vim.api.nvim_buf_clear_namespace(M.list_buf, M.ns, 0, -1)
    vim.api.nvim_buf_set_lines(M.list_buf, 0, -1, false, lines)
    -- highlight flag tokens
    for line, file in pairs(rows) do
        if file.pinned then
            pcall(vim.api.nvim_buf_set_extmark, M.list_buf, M.ns, line - 1, 0, {
                end_line = line,
                line_hl_group = "Special",
                priority = 20,
            })
        end
    end
    vim.bo[M.list_buf].modifiable = false
end

local function path_lines(path, max_lines)
    max_lines = max_lines or 400
    if M._preview_cache[path] then return M._preview_cache[path] end
    local file = io.open(path, "r")
    if not file then
        M._preview_cache[path] = { "(file not readable: " .. path .. ")" }
        return M._preview_cache[path]
    end
    local out = {}
    local count = 0
    for line in file:lines() do
        count = count + 1
        table.insert(out, line)
        if count >= max_lines then
            table.insert(out, string.format("... (truncated at %d lines)", max_lines))
            break
        end
    end
    file:close()
    M._preview_cache[path] = out
    return out
end

local function render_preview()
    if not (M.preview_buf and vim.api.nvim_buf_is_valid(M.preview_buf)) then return end
    if not M._active_path or M._active_path == "" then
        vim.bo[M.preview_buf].modifiable = true
        vim.bo[M.preview_buf].filetype = ""
        vim.api.nvim_buf_set_lines(M.preview_buf, 0, -1, false, { "(select a file on the left)" })
        vim.bo[M.preview_buf].modifiable = false
        return
    end
    local ft = vim.filetype.match({ filename = M._active_path }) or ""
    local lines = path_lines(M._active_path)
    vim.bo[M.preview_buf].modifiable = true
    vim.bo[M.preview_buf].filetype = ft
    vim.api.nvim_buf_set_lines(M.preview_buf, 0, -1, false, lines)
    vim.bo[M.preview_buf].modifiable = false
    if M.preview_win and vim.api.nvim_win_is_valid(M.preview_win) then
        local title = " " .. M._active_path .. " "
        pcall(vim.api.nvim_win_set_config, M.preview_win, { title = title, title_pos = "center" })
    end
end

local function render()
    render_list()
    render_preview()
end

-- ───────────────── RPC ─────────────────

local function set_snapshot(result, err)
    vim.schedule(function()
        if err then
            require("poor-cli.notify").notify("[poor-cli] context: " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        M.snapshot = result or {}
        if not M._active_path and M.snapshot.files and M.snapshot.files[1] then
            M._active_path = tostring(M.snapshot.files[1].path or "")
        end
        render()
    end)
end

function M.refresh() rpc.context_refresh({}, set_snapshot) end

function M.load() rpc.context_snapshot({}, set_snapshot) end

local function current_file()
    if not (M.list_win and vim.api.nvim_win_is_valid(M.list_win)) then return nil end
    local line = vim.api.nvim_win_get_cursor(M.list_win)[1]
    return M.line_rows[line]
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

function M.open_current()
    local file = current_file()
    if not file or file.path == "" then return end
    M.close()
    vim.cmd("edit " .. vim.fn.fnameescape(file.path))
end

-- ───────────────── filter row ─────────────────

local function apply_filter_from_buf()
    if not (M.filter_buf and vim.api.nvim_buf_is_valid(M.filter_buf)) then return end
    local line = vim.api.nvim_buf_get_lines(M.filter_buf, 0, 1, false)[1] or ""
    -- strip trailing newline/whitespace and the leading prompt if present
    line = line:gsub("^/%s*", ""):gsub("^%s+", ""):gsub("%s+$", "")
    M.filter = line
    render_list()
end

local function focus_filter()
    if M.filter_win and vim.api.nvim_win_is_valid(M.filter_win) then
        vim.api.nvim_set_current_win(M.filter_win)
        vim.cmd("startinsert!")
    end
end

local function focus_list()
    if M.list_win and vim.api.nvim_win_is_valid(M.list_win) then
        vim.api.nvim_set_current_win(M.list_win)
        vim.cmd("stopinsert")
    end
end

-- ───────────────── window plumbing ─────────────────

local function make_scratch(name, ft, modifiable)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "hide"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = ft or "markdown"
    vim.bo[buf].modifiable = modifiable ~= false
    pcall(vim.api.nvim_buf_set_name, buf, name)
    return buf
end

function M.close()
    for _, win in ipairs({ M.filter_win, M.list_win, M.preview_win }) do
        if win and vim.api.nvim_win_is_valid(win) then
            pcall(vim.api.nvim_win_close, win, true)
        end
    end
    M.filter_win, M.list_win, M.preview_win = nil, nil, nil
    M._preview_cache = {}
end

function M.open()
    if M.list_win and vim.api.nvim_win_is_valid(M.list_win) then
        vim.api.nvim_set_current_win(M.list_win)
        M.refresh()
        return
    end

    M.list_buf = make_scratch("[poor-cli context]", "poor-cli-context", false)
    M.preview_buf = make_scratch("[poor-cli context preview]", "", false)
    M.filter_buf = make_scratch("[poor-cli context filter]", "poor-cli-context-filter", true)
    vim.api.nvim_buf_set_lines(M.filter_buf, 0, -1, false, { "" })

    local panel_width = math.min(140, vim.o.columns - 4)
    local panel_height = math.max(24, vim.o.lines - 4)
    local list_width = math.max(50, math.floor(panel_width * 0.5))
    local preview_width = panel_width - list_width - 1
    local row = math.floor((vim.o.lines - panel_height) / 2)
    local col = math.floor((vim.o.columns - panel_width) / 2)

    -- filter row: 1-line floating win pinned to top of list pane
    M.filter_win = vim.api.nvim_open_win(M.filter_buf, false, {
        relative = "editor",
        width = list_width,
        height = 1,
        row = row,
        col = col,
        border = "rounded",
        style = "minimal",
        title = " / filter ",
        title_pos = "left",
    })
    vim.wo[M.filter_win].wrap = false
    vim.wo[M.filter_win].signcolumn = "no"

    M.list_win = vim.api.nvim_open_win(M.list_buf, true, {
        relative = "editor",
        width = list_width,
        height = panel_height - 3,
        row = row + 3,
        col = col,
        border = "rounded",
        style = "minimal",
        title = " files ",
        title_pos = "center",
    })
    vim.wo[M.list_win].wrap = false
    vim.wo[M.list_win].cursorline = true
    vim.wo[M.list_win].signcolumn = "no"

    M.preview_win = vim.api.nvim_open_win(M.preview_buf, false, {
        relative = "editor",
        width = preview_width,
        height = panel_height,
        row = row,
        col = col + list_width + 1,
        border = "rounded",
        style = "minimal",
        title = " preview ",
        title_pos = "center",
        footer = " p pin · d drop · o open · / filter · r refresh · q close ",
        footer_pos = "center",
    })
    vim.wo[M.preview_win].wrap = false
    vim.wo[M.preview_win].number = true
    vim.wo[M.preview_win].signcolumn = "no"

    -- list keymaps
    vim.keymap.set("n", "q", M.close, { buffer = M.list_buf, nowait = true })
    vim.keymap.set("n", "<Esc>", M.close, { buffer = M.list_buf, nowait = true })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.list_buf, nowait = true })
    vim.keymap.set("n", "p", M.pin_current, { buffer = M.list_buf, nowait = true })
    vim.keymap.set("n", "d", M.drop_current, { buffer = M.list_buf, nowait = true })
    vim.keymap.set("n", "o", M.open_current, { buffer = M.list_buf, nowait = true })
    vim.keymap.set("n", "/", focus_filter, { buffer = M.list_buf, nowait = true })

    -- filter keymaps: <Esc>/<CR> return focus to list; typing updates preview
    vim.keymap.set({ "i", "n" }, "<Esc>", focus_list, { buffer = M.filter_buf, nowait = true })
    vim.keymap.set({ "i", "n" }, "<CR>", focus_list, { buffer = M.filter_buf, nowait = true })

    -- live filter on text changes in filter buf
    vim.api.nvim_create_autocmd({ "TextChanged", "TextChangedI" }, {
        buffer = M.filter_buf,
        group = vim.api.nvim_create_augroup("poor-cli-context-filter", { clear = true }),
        callback = apply_filter_from_buf,
    })

    -- cursor-synced preview on list buf
    vim.api.nvim_create_autocmd("CursorMoved", {
        buffer = M.list_buf,
        group = vim.api.nvim_create_augroup("poor-cli-context-cursor", { clear = true }),
        callback = function()
            local file = current_file()
            if file and file.path ~= M._active_path then
                M._active_path = file.path
                render_preview()
            end
        end,
    })

    -- close all panes together
    for _, win in ipairs({ M.list_win, M.preview_win, M.filter_win }) do
        vim.api.nvim_create_autocmd("WinClosed", {
            pattern = tostring(win),
            once = true,
            callback = vim.schedule_wrap(function() M.close() end),
        })
    end

    M.load()
end

return M
