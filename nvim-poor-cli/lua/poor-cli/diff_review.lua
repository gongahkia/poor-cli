local rpc = require("poor-cli.rpc")
local config = require("poor-cli.config")

local M = {
    ns = vim.api.nvim_create_namespace("poor-cli-diff-review"),
    buf = nil,
    win = nil,
    rows = {},
    edits = {},
    edit_lines = {},
    layout = nil,
}

local function cfg()
    return config.get("diff_review") or {}
end

local function s(value)
    return tostring(value or "")
end

local function clip(value, width)
    local text = s(value):gsub("\n", " ")
    if #text <= width then return text end
    return text:sub(1, math.max(width - 3, 1)) .. "..."
end

local function edit_id(edit)
    return edit.editId or edit.edit_id or ""
end

local function hunk_id(hunk)
    return hunk.hunkId or hunk.hunk_id or ""
end

local function hunk_at_cursor()
    local row = M.rows[vim.api.nvim_win_get_cursor(0)[1]]
    if row and row.hunk then return row.edit, row.hunk end
    return nil, nil
end

local function edit_at_cursor()
    local row = M.rows[vim.api.nvim_win_get_cursor(0)[1]]
    if row and row.edit then return row.edit end
    if #M.edits > 0 then return M.edits[1] end
    return nil
end

local function set_lines(lines)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    for line, row in pairs(M.rows) do
        if row.hunk then
            local status = row.hunk.status or "pending"
            local hl = status == "accepted" and "DiagnosticOk" or status == "rejected" and "DiagnosticError" or "DiagnosticWarn"
            vim.api.nvim_buf_set_extmark(M.buf, M.ns, line - 1, 0, {
                virt_text = { { "[" .. status .. "]", hl } },
                virt_text_pos = "eol",
            })
        end
    end
    vim.bo[M.buf].modifiable = false
end

local function render()
    M.rows = {}
    M.edit_lines = {}
    local help = "ga accept hunk | gr reject hunk | gA accept edit | gR reject edit | gc regen | gl layout | gf file | q close"
    local lines = {
        "# poor-cli diff review",
        "",
        help,
        "",
    }
    if #M.edits == 0 then
        table.insert(lines, "no pending edits")
        return lines
    end
    for index, edit in ipairs(M.edits) do
        local id = edit_id(edit)
        table.insert(lines, string.format("[%d/%d] %s (%d hunks)", index, #M.edits, s(edit.path), #(edit.hunks or {})))
        M.rows[#lines] = { edit = edit }
        M.edit_lines[id] = #lines
        table.insert(lines, "Prompt: \"" .. clip(edit.prompt, 100) .. "\"")
        table.insert(lines, "Status: " .. s(edit.status or "pending"))
        for _, hunk in ipairs(edit.hunks or {}) do
            table.insert(lines, "")
            table.insert(lines, s(hunk.header))
            M.rows[#lines] = { edit = edit, hunk = hunk, kind = "hunk" }
            local before = s(hunk.before)
            for line in (before .. "\n"):gmatch("(.-)\n") do
                if line ~= "" then table.insert(lines, "-" .. line) end
            end
            local after = s(hunk.after)
            for line in (after .. "\n"):gmatch("(.-)\n") do
                if line ~= "" then table.insert(lines, "+" .. line) end
            end
        end
        table.insert(lines, "")
    end
    return lines
end

function M.refresh()
    rpc.diff_list(function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] diff review: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            M.edits = (result or {}).edits or {}
            set_lines(render())
        end)
    end)
end

local function wipe_named_buffer(name)
    local existing = vim.fn.bufnr(name)
    if existing == -1 then return end
    for _, win in ipairs(vim.fn.win_findbuf(existing)) do
        pcall(vim.api.nvim_win_set_buf, win, vim.api.nvim_create_buf(false, true))
    end
    pcall(vim.api.nvim_buf_delete, existing, { force = true })
end

local function ensure_buf()
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then return M.buf end
    wipe_named_buffer("[poor-cli diff review]")
    M.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[M.buf].buftype = "nofile"
    vim.bo[M.buf].bufhidden = "hide"
    vim.bo[M.buf].swapfile = false
    vim.bo[M.buf].filetype = "diff"
    vim.api.nvim_buf_set_name(M.buf, "[poor-cli diff review]")
    return M.buf
end

local function map(lhs, fn, desc)
    vim.keymap.set("n", lhs, fn, { buffer = M.buf, silent = true, nowait = true, desc = desc })
end

function M.open()
    local buf = ensure_buf()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
    else
        local width = tonumber(cfg().panel_width) or 100
        local float_win = require("poor-cli.float_win")
        M.win = float_win.open(buf, {
            width = math.min(width, vim.o.columns - 4),
            height = math.max(24, vim.o.lines - 4),
            position = "center",
            title = " poor-cli diff review ",
            close_keys = {},
            wrap = false,
        })
    end
    map("q", M.close, "close diff review")
    map("<Esc>", M.close, "close diff review")
    map("r", M.refresh, "refresh diff review")
    map("a", M.accept_hunk, "accept hunk")
    map("ga", M.accept_hunk, "accept hunk")
    map("gr", M.reject_hunk, "reject hunk")
    map("gA", M.accept_edit, "accept edit")
    map("gR", M.reject_edit, "reject edit")
    map("gc", M.regen_hunk, "regenerate hunk")
    map("gl", M.toggle_layout, "toggle diff layout")
    map("gf", M.goto_file, "jump to file")
    map("gn", M.next_hunk, "next hunk")
    map("gp", M.prev_hunk, "previous hunk")
    map("]e", M.next_edit, "next edit")
    map("[e", M.prev_edit, "previous edit")
    M.refresh()
    return buf
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
    M.win = nil
end

function M.toggle()
    if M.win and vim.api.nvim_win_is_valid(M.win) then M.close() else M.open() end
end

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
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
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
    local edit = edit_at_cursor()
    if not edit then return false end
    refresh_after("diff.accept", { editId = edit_id(edit) })
    return true
end

function M.reject_edit()
    local edit = edit_at_cursor()
    if not edit then return false end
    refresh_after("diff.reject", { editId = edit_id(edit) })
    return true
end

function M.regen_hunk()
    local edit, hunk = hunk_at_cursor()
    if not edit or not hunk then return false end
    local instruction = vim.fn.input("regenerate: ")
    refresh_after("diff.regen", { editId = edit_id(edit), hunkId = hunk_id(hunk), instruction = instruction, newContent = instruction })
    return true
end

local function move_to_row(predicate, step)
    local row = vim.api.nvim_win_get_cursor(0)[1] + step
    while row >= 1 and row <= vim.api.nvim_buf_line_count(M.buf) do
        if predicate(M.rows[row]) then
            vim.api.nvim_win_set_cursor(0, { row, 0 })
            return true
        end
        row = row + step
    end
    return false
end

function M.next_hunk() return move_to_row(function(row) return row and row.hunk end, 1) end
function M.prev_hunk() return move_to_row(function(row) return row and row.hunk end, -1) end
function M.next_edit() return move_to_row(function(row) return row and row.edit and not row.hunk end, 1) end
function M.prev_edit() return move_to_row(function(row) return row and row.edit and not row.hunk end, -1) end

function M.goto_file()
    local edit, hunk = hunk_at_cursor()
    edit = edit or edit_at_cursor()
    if not edit or not edit.path then return false end
    vim.cmd("edit " .. vim.fn.fnameescape(edit.path))
    local line = tonumber(hunk and (hunk.lineStart or hunk.line_start)) or 1
    pcall(vim.api.nvim_win_set_cursor, 0, { math.max(line, 1), 0 })
    return true
end

function M.toggle_layout()
    M.layout = (M.layout or cfg().layout or "unified") == "unified" and "side_by_side" or "unified"
    if M.layout == "side_by_side" then
        local edit = edit_at_cursor()
        if edit then
            local left = vim.api.nvim_create_buf(false, true)
            local right = vim.api.nvim_create_buf(false, true)
            vim.bo[left].buftype, vim.bo[right].buftype = "nofile", "nofile"
            vim.api.nvim_buf_set_lines(left, 0, -1, false, vim.split(s(edit.original), "\n", { plain = true }))
            vim.api.nvim_buf_set_lines(right, 0, -1, false, vim.split(s(edit.proposed), "\n", { plain = true }))
            vim.cmd("botright vsplit")
            vim.api.nvim_win_set_buf(0, left)
            vim.cmd("diffthis")
            vim.cmd("rightbelow vsplit")
            vim.api.nvim_win_set_buf(0, right)
            vim.cmd("diffthis")
        end
    end
    return M.layout
end

function M.setup()
    M.layout = cfg().layout or "unified"
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
            if M.buf and vim.api.nvim_buf_is_valid(M.buf) then M.refresh() end
        end,
    })
end

return M
