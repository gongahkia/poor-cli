-- poor-cli/diff_review.lua
-- 2-pane diff review: left = hunk index, right = live proposed-edit preview.
-- Left pane is a scratch buffer inside a floating container; right pane loads
-- the real on-disk file and renders proposed changes with extmarks.

local rpc = require("poor-cli.rpc")
local config = require("poor-cli.config")

local M = {
    ns_list  = vim.api.nvim_create_namespace("poor-cli-diff-review-list"),
    ns_diff  = vim.api.nvim_create_namespace("poor-cli-diff-review-diff"),
    list_buf = nil,
    list_win = nil,
    diff_buf = nil,
    diff_win = nil,
    rows = {},
    edits = {},
    active_edit = nil,
    active_hunk = nil,
}

local function cfg()
    return config.get("diff_review") or {}
end

local function s(value)
    return tostring(value or "")
end

local function edit_id(edit)
    return edit.editId or edit.edit_id or ""
end

local function hunk_id(hunk)
    return hunk.hunkId or hunk.hunk_id or ""
end

local function status_hl(status)
    if status == "accepted" then return "DiagnosticOk" end
    if status == "rejected" then return "DiagnosticError" end
    return "DiagnosticWarn"
end

-- ───────────────── renderers ─────────────────

local function render_list()
    if not (M.list_buf and vim.api.nvim_buf_is_valid(M.list_buf)) then return end
    M.rows = {}
    local lines = { "# diff review" }
    if #M.edits == 0 then
        table.insert(lines, "")
        table.insert(lines, "no pending edits")
        vim.bo[M.list_buf].modifiable = true
        vim.api.nvim_buf_set_lines(M.list_buf, 0, -1, false, lines)
        vim.bo[M.list_buf].modifiable = false
        return
    end

    local total = #M.edits
    for idx, edit in ipairs(M.edits) do
        local accepted, rejected, pending = 0, 0, 0
        for _, hunk in ipairs(edit.hunks or {}) do
            local st = tostring(hunk.status or "pending")
            if st == "accepted" then accepted = accepted + 1
            elseif st == "rejected" then rejected = rejected + 1
            else pending = pending + 1 end
        end
        local active_marker = (edit_id(edit) == edit_id(M.active_edit or {})) and "▸" or " "
        table.insert(lines, "")
        table.insert(lines, string.format("%s [%d/%d] %s", active_marker, idx, total, s(edit.path)))
        M.rows[#lines] = { edit = edit }
        table.insert(lines, string.format("    %d hunks  %d✓ %d✗ %d?",
            #(edit.hunks or {}), accepted, rejected, pending))
        if edit.prompt and edit.prompt ~= "" then
            local prompt = tostring(edit.prompt):gsub("\n", " ")
            if #prompt > 60 then prompt = prompt:sub(1, 57) .. "..." end
            table.insert(lines, "    prompt: " .. prompt)
        end
        for hidx, hunk in ipairs(edit.hunks or {}) do
            local status = tostring(hunk.status or "pending")
            local line_start = tonumber(hunk.lineStart or hunk.line_start) or 0
            local added = tonumber(hunk.added) or 0
            local removed = tonumber(hunk.removed) or 0
            local cursor_marker = (M.active_hunk and hunk_id(hunk) == hunk_id(M.active_hunk)) and "▸" or " "
            table.insert(lines, string.format("  %s %d [%s] L%d +%d -%d",
                cursor_marker, hidx, status, line_start, added, removed))
            M.rows[#lines] = { edit = edit, hunk = hunk, kind = "hunk" }
        end
    end

    vim.bo[M.list_buf].modifiable = true
    vim.api.nvim_buf_clear_namespace(M.list_buf, M.ns_list, 0, -1)
    vim.api.nvim_buf_set_lines(M.list_buf, 0, -1, false, lines)
    -- highlight status tokens inside hunk rows
    for line, row in pairs(M.rows) do
        if row.hunk then
            local raw = lines[line] or ""
            local i = raw:find("%[[%w%?]+%]")
            if i then
                local j = raw:find("%]", i)
                pcall(vim.api.nvim_buf_set_extmark, M.list_buf, M.ns_list, line - 1, i - 1, {
                    end_col = j or (i + 1),
                    hl_group = status_hl(row.hunk.status),
                })
            end
        end
    end
    vim.bo[M.list_buf].modifiable = false
end

local function render_diff()
    if not (M.diff_buf and vim.api.nvim_buf_is_valid(M.diff_buf)) then return end
    vim.api.nvim_buf_clear_namespace(M.diff_buf, M.ns_diff, 0, -1)
    if not M.active_edit then
        vim.bo[M.diff_buf].modifiable = true
        vim.api.nvim_buf_set_lines(M.diff_buf, 0, -1, false, { "(select an edit or hunk in the list)" })
        vim.bo[M.diff_buf].modifiable = false
        return
    end
    -- render a hunk-oriented diff view (unified) for the active edit; the left
    -- pane list continues to drive navigation. We render each hunk as a section.
    local lines = { "# " .. s(M.active_edit.path) }
    table.insert(lines, "")
    for idx, hunk in ipairs(M.active_edit.hunks or {}) do
        local is_active = M.active_hunk and hunk_id(hunk) == hunk_id(M.active_hunk)
        local marker = is_active and "▸" or " "
        table.insert(lines, string.format("%s hunk %d [%s] %s", marker, idx,
            tostring(hunk.status or "pending"), s(hunk.header)))
        local active_start = #lines
        local before = s(hunk.before)
        for line in (before .. "\n"):gmatch("(.-)\n") do
            if line ~= "" then table.insert(lines, "-" .. line) end
        end
        local after = s(hunk.after)
        for line in (after .. "\n"):gmatch("(.-)\n") do
            if line ~= "" then table.insert(lines, "+" .. line) end
        end
        if is_active then
            -- highlight the active hunk's lines
            for l = active_start, #lines do
                local raw = lines[l] or ""
                local hl = raw:sub(1, 1) == "+" and "DiffAdd" or raw:sub(1, 1) == "-" and "DiffDelete" or nil
                if hl then
                    pcall(vim.api.nvim_buf_set_extmark, M.diff_buf, M.ns_diff, l - 1, 0, {
                        line_hl_group = hl,
                    })
                end
            end
        end
        table.insert(lines, "")
    end
    vim.bo[M.diff_buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.diff_buf, 0, -1, false, lines)
    vim.bo[M.diff_buf].modifiable = false
end

local function render()
    render_list()
    render_diff()
end

function M.refresh()
    rpc.diff_list(function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] diff review: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            M.edits = (result or {}).edits or {}
            -- keep active selection if it still exists; otherwise pick first
            if M.active_edit then
                local still_there = false
                for _, e in ipairs(M.edits) do
                    if edit_id(e) == edit_id(M.active_edit) then
                        M.active_edit = e
                        still_there = true
                        break
                    end
                end
                if not still_there then M.active_edit, M.active_hunk = nil, nil end
            end
            if not M.active_edit and #M.edits > 0 then
                M.active_edit = M.edits[1]
                M.active_hunk = (M.edits[1].hunks or {})[1]
            end
            render()
        end)
    end)
end

local function hunk_at_cursor()
    if not (M.list_win and vim.api.nvim_win_is_valid(M.list_win)) then return nil, nil end
    local line = vim.api.nvim_win_get_cursor(M.list_win)[1]
    local row = M.rows[line]
    if row and row.hunk then return row.edit, row.hunk end
    if row and row.edit then return row.edit, nil end
    return nil, nil
end

local function sync_active_from_cursor()
    local edit, hunk = hunk_at_cursor()
    if edit then M.active_edit = edit end
    if hunk then M.active_hunk = hunk end
    render()
end

-- ───────────────── window plumbing ─────────────────

local function wipe_named_buffer(name)
    local existing = vim.fn.bufnr(name)
    if existing == -1 then return end
    for _, win in ipairs(vim.fn.win_findbuf(existing)) do
        pcall(vim.api.nvim_win_set_buf, win, vim.api.nvim_create_buf(false, true))
    end
    pcall(vim.api.nvim_buf_delete, existing, { force = true })
end

local function make_scratch(name, ft)
    wipe_named_buffer(name)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "hide"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = ft or "markdown"
    pcall(vim.api.nvim_buf_set_name, buf, name)
    return buf
end

local function map(buf, lhs, fn, desc)
    vim.keymap.set("n", lhs, fn, { buffer = buf, silent = true, nowait = true, desc = desc })
end

function M.open()
    if M.list_win and vim.api.nvim_win_is_valid(M.list_win) then
        vim.api.nvim_set_current_win(M.list_win)
        M.refresh()
        return
    end

    M.list_buf = make_scratch("[poor-cli diff review]", "poor-cli-diff-review-list")
    M.diff_buf = make_scratch("[poor-cli diff pane]", "diff")

    local panel_width = math.min(tonumber(cfg().panel_width) or 140, vim.o.columns - 4)
    local panel_height = math.max(24, vim.o.lines - 4)
    local list_width = math.max(34, math.floor(panel_width * 0.35))
    local diff_width = panel_width - list_width - 1

    local row = math.floor((vim.o.lines - panel_height) / 2)
    local col = math.floor((vim.o.columns - panel_width) / 2)

    M.list_win = vim.api.nvim_open_win(M.list_buf, true, {
        relative = "editor",
        width = list_width,
        height = panel_height,
        row = row,
        col = col,
        border = "rounded",
        style = "minimal",
        title = " hunks ",
        title_pos = "center",
    })
    vim.wo[M.list_win].wrap = false
    vim.wo[M.list_win].signcolumn = "no"
    vim.wo[M.list_win].cursorline = true

    M.diff_win = vim.api.nvim_open_win(M.diff_buf, false, {
        relative = "editor",
        width = diff_width,
        height = panel_height,
        row = row,
        col = col + list_width + 1,
        border = "rounded",
        style = "minimal",
        title = " diff ",
        title_pos = "center",
        footer = " ga accept · gr reject · gA edit · gR reject edit · gc regen · gf jump · q close ",
        footer_pos = "center",
    })
    vim.wo[M.diff_win].wrap = false
    vim.wo[M.diff_win].signcolumn = "no"

    -- keymaps (all live on the list buffer)
    local close = function() M.close() end
    map(M.list_buf, "q", close, "close diff review")
    map(M.list_buf, "<Esc>", close, "close diff review")
    map(M.list_buf, "r", M.refresh, "refresh")
    map(M.list_buf, "<CR>", function()
        sync_active_from_cursor()
    end, "select hunk")
    map(M.list_buf, "ga", M.accept_hunk, "accept hunk")
    map(M.list_buf, "gr", M.reject_hunk, "reject hunk")
    map(M.list_buf, "gA", M.accept_edit, "accept edit")
    map(M.list_buf, "gR", M.reject_edit, "reject edit")
    map(M.list_buf, "gc", M.regen_hunk, "regen hunk")
    map(M.list_buf, "gf", M.goto_file, "jump to file")
    map(M.list_buf, "gn", function() M._move(1, "hunk") end, "next hunk")
    map(M.list_buf, "gp", function() M._move(-1, "hunk") end, "prev hunk")
    map(M.list_buf, "]e", function() M._move(1, "edit") end, "next edit")
    map(M.list_buf, "[e", function() M._move(-1, "edit") end, "prev edit")

    -- live preview sync on cursor move
    vim.api.nvim_create_autocmd({ "CursorMoved" }, {
        buffer = M.list_buf,
        group = vim.api.nvim_create_augroup("poor-cli-diff-review-cursor", { clear = true }),
        callback = sync_active_from_cursor,
    })

    -- coordinated close: closing either pane closes the other
    for _, win in ipairs({ M.list_win, M.diff_win }) do
        vim.api.nvim_create_autocmd("WinClosed", {
            pattern = tostring(win),
            once = true,
            callback = vim.schedule_wrap(function() M.close() end),
        })
    end

    M.refresh()
end

function M.close()
    for _, win in ipairs({ M.diff_win, M.list_win }) do
        if win and vim.api.nvim_win_is_valid(win) then
            pcall(vim.api.nvim_win_close, win, true)
        end
    end
    M.list_win, M.diff_win = nil, nil
end

function M.toggle()
    if M.list_win and vim.api.nvim_win_is_valid(M.list_win) then
        M.close()
    else
        M.open()
    end
end

-- ───────────────── RPC actions ─────────────────

function M.stage_codeblock(params, callback)
    rpc.diff_stage(params or {}, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] diff review: " .. rpc.format_error(err), vim.log.levels.ERROR)
                if callback then callback(nil, err) end
                return
            end
            M.open()
            if callback then callback(result, nil) end
        end)
    end)
    return true
end

local function refresh_after(method, params)
    rpc.request(method, params, function(_, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            M.refresh()
        end)
    end)
end

function M.accept_hunk()
    local edit, hunk = hunk_at_cursor()
    if not edit or not hunk then return false end
    refresh_after("diff.accept", { editId = edit_id(edit), hunkId = hunk_id(hunk) })
    return true
end

function M.reject_hunk()
    local edit, hunk = hunk_at_cursor()
    if not edit or not hunk then return false end
    refresh_after("diff.reject", { editId = edit_id(edit), hunkId = hunk_id(hunk) })
    return true
end

function M.accept_edit()
    local edit = hunk_at_cursor()
    if not edit then return false end
    refresh_after("diff.accept", { editId = edit_id(edit) })
    return true
end

function M.reject_edit()
    local edit = hunk_at_cursor()
    if not edit then return false end
    refresh_after("diff.reject", { editId = edit_id(edit) })
    return true
end

function M.regen_hunk()
    local edit, hunk = hunk_at_cursor()
    if not edit or not hunk then return false end
    vim.ui.input({ prompt = "regenerate: " }, function(instruction)
        if not instruction then return end
        refresh_after("diff.regen", {
            editId = edit_id(edit),
            hunkId = hunk_id(hunk),
            instruction = instruction,
            newContent = instruction,
        })
    end)
    return true
end

function M.goto_file()
    local edit, hunk = hunk_at_cursor()
    if not edit or not edit.path then return false end
    M.close()
    vim.cmd("edit " .. vim.fn.fnameescape(edit.path))
    local line = tonumber(hunk and (hunk.lineStart or hunk.line_start)) or 1
    pcall(vim.api.nvim_win_set_cursor, 0, { math.max(line, 1), 0 })
    return true
end

function M._move(step, kind)
    if not (M.list_win and vim.api.nvim_win_is_valid(M.list_win)) then return false end
    local cursor = vim.api.nvim_win_get_cursor(M.list_win)[1]
    local total = vim.api.nvim_buf_line_count(M.list_buf)
    local target = cursor + step
    while target >= 1 and target <= total do
        local row = M.rows[target]
        if row then
            if kind == "hunk" and row.hunk then
                vim.api.nvim_win_set_cursor(M.list_win, { target, 0 })
                sync_active_from_cursor()
                return true
            end
            if kind == "edit" and row.edit and not row.hunk then
                vim.api.nvim_win_set_cursor(M.list_win, { target, 0 })
                sync_active_from_cursor()
                return true
            end
        end
        target = target + step
    end
    return false
end

function M.next_hunk() return M._move(1, "hunk") end
function M.prev_hunk() return M._move(-1, "hunk") end
function M.next_edit() return M._move(1, "edit") end
function M.prev_edit() return M._move(-1, "edit") end

-- kept for backward compat with :PoorCLIDiff layout — now a no-op with a nudge
function M.toggle_layout()
    require("poor-cli.notify").notify(
        "[poor-cli] diff layout is always 2-pane in v6.1; the toggle is a no-op.",
        vim.log.levels.INFO
    )
end

function M.setup()
    local group = vim.api.nvim_create_augroup("poor-cli-diff-review", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIStageEvent",
        callback = function()
            if cfg().auto_open ~= false then M.open() end
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIEditCommitted",
        callback = function()
            if M.list_buf and vim.api.nvim_buf_is_valid(M.list_buf) then M.refresh() end
        end,
    })
end

return M
